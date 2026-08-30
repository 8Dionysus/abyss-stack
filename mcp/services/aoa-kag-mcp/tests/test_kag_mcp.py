from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

from aoa_kag_mcp.canonical import CanonicalRepoKag
from aoa_kag_mcp.core import AoAKagMCPState
from aoa_kag_mcp.server import build_server


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _state(root: Path) -> AoAKagMCPState:
    aoa_kag = root / "aoa-kag"
    owner = root / "connectors" / "repo-a"
    _write_json(
        aoa_kag / "generated" / "local_kag_provider_map.min.json",
        {
            "schema_version": "aoa-local-kag-provider-map-v1",
            "providers": [
                {
                    "repo": "repo-a",
                    "provider_status": "provider_ready",
                    "manifest_ref": "kag/manifest.json",
                    "repo_local_index": {
                        "source_index_ref": "kag/indexes/source_surface_index.json"
                    },
                }
            ],
            "mcp_handoff": {"service_route": "abyss-stack/mcp/services/aoa-kag-mcp"},
        },
    )
    _write_json(
        aoa_kag / "manifests" / "local_kag_readiness.json",
        {
            "os_surfaces": [
                {
                    "surface_id": "connectors/repo-a",
                    "root": (root / "runtime-copy" / "repo-a").as_posix(),
                    "provider_status": "runtime_consumer",
                    "owner_return_route": {"repo": "repo-a"},
                },
                {
                    "surface_id": "connectors/repo-a",
                    "root": owner.as_posix(),
                    "provider_status": "provider_ready",
                    "owner_return_route": {"repo": "repo-a"},
                },
            ]
        },
    )
    _write_json(
        aoa_kag / "generated" / "repo_local_kag_coverage.min.json",
        {"owners": [{"repo": "repo-a", "index_status": "passed"}]},
    )
    _write_json(
        owner / "kag" / "manifest.json",
        {"schema_version": "aoa_repo_kag_manifest_v1", "repo": "repo-a"},
    )
    _write_json(
        owner / "kag" / "indexes" / "source_surface_index.json",
        {
            "schema_version": "aoa-repo-local-kag-index-v1",
            "index_identity": {"content_digest": "fixture-digest"},
            "records": [],
        },
    )
    return AoAKagMCPState.discover(
        workspace_root=root,
        aoa_kag_root=aoa_kag,
    )


def _use_portable_family(state: AoAKagMCPState) -> Path:
    provider_map = state.provider_map()
    packet = provider_map["providers"][0]["repo_local_index"]
    packet["family_storage"] = "v3-portable-shards"
    packet["portable_family"] = {
        "manifest_ref": "kag/indexes/index_family.manifest.json",
    }
    _write_json(state.provider_map_path, provider_map)
    source_index = state.source_index_path("repo-a")
    assert source_index is not None
    source_index.unlink()
    manifest = source_index.with_name("index_family.manifest.json")
    _write_json(
        manifest,
        {
            "schema_version": "aoa-repo-local-kag-family-v3",
            "family_identity": {
                "content_digest": "portable-family-fixture-digest",
                "source_snapshot": "sha256:portable-source-fixture-digest",
            },
            "source_index_header": {
                "index_identity": {
                    "content_digest": "portable-source-fixture-digest",
                }
            },
            "compatibility": {
                "files": [
                    {
                        "kind": "source",
                        "content_digest": "portable-source-fixture-digest",
                    }
                ]
            },
        },
    )
    return manifest


def test_state_resolves_canonical_owner_surfaces(tmp_path: Path) -> None:
    state = _state(tmp_path)

    assert (
        state.provider_root("repo-a") == (tmp_path / "connectors" / "repo-a").resolve()
    )
    assert (
        state.source_index_path("repo-a")
        == (
            tmp_path
            / "connectors"
            / "repo-a"
            / "kag"
            / "indexes"
            / "source_surface_index.json"
        ).resolve()
    )
    assert state.provider_manifest("repo-a") == {
        "schema_version": "aoa_repo_kag_manifest_v1",
        "repo": "repo-a",
    }


def test_state_prefers_clean_pinned_provider_checkout(tmp_path: Path) -> None:
    state = _state(tmp_path)
    canonical_owner = state.aoa_kag_root / ".deps" / "repo-a"
    _write_json(
        canonical_owner / "kag" / "manifest.json",
        {"schema_version": "aoa_repo_kag_manifest_v1", "repo": "repo-a"},
    )
    _write_json(
        canonical_owner / "kag" / "indexes" / "source_surface_index.json",
        {
            "schema_version": "aoa-repo-local-kag-index-v1",
            "index_identity": {"content_digest": "pinned-fixture-digest"},
            "records": [],
        },
    )

    refreshed = AoAKagMCPState.discover(
        workspace_root=state.workspace_root,
        aoa_kag_root=state.aoa_kag_root,
    )

    assert refreshed.provider_root("repo-a") == canonical_owner.resolve()
    assert CanonicalRepoKag(refreshed).owner_digest("repo-a") == (
        "pinned-fixture-digest"
    )


def test_state_honors_explicit_canonical_provider_root(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    canonical_root = tmp_path / "provider-cache"
    canonical_owner = canonical_root / "repo-a"
    _write_json(
        canonical_owner / "kag" / "indexes" / "source_surface_index.json",
        {
            "schema_version": "aoa-repo-local-kag-index-v1",
            "index_identity": {"content_digest": "explicit-fixture-digest"},
            "records": [],
        },
    )

    refreshed = AoAKagMCPState.discover(
        workspace_root=state.workspace_root,
        aoa_kag_root=state.aoa_kag_root,
        canonical_provider_root=canonical_root,
    )

    assert refreshed.provider_root("repo-a") == canonical_owner.resolve()
    assert CanonicalRepoKag(refreshed).owner_digest("repo-a") == (
        "explicit-fixture-digest"
    )


def test_state_honors_absolute_artifact_root_and_rejects_relative_root(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    artifact_root = tmp_path / "cold-cas"
    refreshed = AoAKagMCPState.discover(
        workspace_root=state.workspace_root,
        aoa_kag_root=state.aoa_kag_root,
        artifact_root=artifact_root,
    )

    assert refreshed.artifact_root == artifact_root.resolve()
    with pytest.raises(ValueError, match="absolute path"):
        AoAKagMCPState.discover(
            workspace_root=state.workspace_root,
            aoa_kag_root=state.aoa_kag_root,
            artifact_root="relative-cas",
        )


def test_state_resolves_portable_family_identity(tmp_path: Path) -> None:
    state = _state(tmp_path)
    manifest = _use_portable_family(state)

    assert state.canonical_family_path("repo-a") == manifest.resolve()
    assert CanonicalRepoKag(state).owner_digest("repo-a") == (
        "portable-source-fixture-digest"
    )


def test_state_rejects_disagreeing_portable_source_identities(tmp_path: Path) -> None:
    state = _state(tmp_path)
    manifest = _use_portable_family(state)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["source_index_header"]["index_identity"]["content_digest"] = (
        "different-source-fixture-digest"
    )
    _write_json(manifest, payload)

    with pytest.raises(RuntimeError, match="source-index identities disagree"):
        CanonicalRepoKag(state).owner_digest("repo-a")


def test_state_keeps_reads_inside_provider_root(tmp_path: Path) -> None:
    state = _state(tmp_path)
    provider_map = state.provider_map()
    provider_map["providers"][0]["repo_local_index"]["source_index_ref"] = (
        "../outside.json"
    )
    _write_json(state.provider_map_path, provider_map)

    with pytest.raises(ValueError, match="escapes provider root"):
        state.source_index_path("repo-a")


def test_state_keeps_portable_manifest_inside_provider_root(tmp_path: Path) -> None:
    state = _state(tmp_path)
    provider_map = state.provider_map()
    packet = provider_map["providers"][0]["repo_local_index"]
    packet["family_storage"] = "v3-portable-shards"
    packet["portable_family"] = {"manifest_ref": "../../outside.json"}
    _write_json(state.provider_map_path, provider_map)
    source_index = state.source_index_path("repo-a")
    assert source_index is not None
    source_index.unlink()

    with pytest.raises(ValueError, match="escapes provider root"):
        state.canonical_family_path("repo-a")


def test_canonical_query_module_is_loaded_from_owner_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(tmp_path)
    query_path = state.aoa_kag_root / "scripts" / "query_repo_local_kag.py"
    query_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.write_text(
        "MARKER = 'owner-root'\n"
        "class RepoKagQuery:\n"
        "    pass\n"
        "def load_family(repo_root):\n"
        "    return {}, {}\n",
        encoding="utf-8",
    )
    foreign = types.ModuleType("scripts.query_repo_local_kag")
    foreign.MARKER = "foreign-module"
    monkeypatch.setitem(sys.modules, "scripts.query_repo_local_kag", foreign)

    module = CanonicalRepoKag(state)._query_module()

    assert module.MARKER == "owner-root"


def test_canonical_query_loads_portable_family_without_v2_monolith(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    _use_portable_family(state)
    query_path = state.aoa_kag_root / "scripts" / "query_repo_local_kag.py"
    query_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.write_text(
        "SEEN = {}\n"
        "class RepoKagQuery:\n"
        "    def __init__(self, source_index, family, repo_root=None):\n"
        "        self.source_index = source_index\n"
        "    def discover(self):\n"
        "        return {'storage': self.source_index['storage']}\n"
        "def load_family(repo_root, **kwargs):\n"
        "    SEEN['kwargs'] = kwargs\n"
        "    return {'storage': 'portable-v3'}, {}, None, None\n",
        encoding="utf-8",
    )

    canonical = CanonicalRepoKag(state)
    assert canonical.discover_owner("repo-a") == {
        "storage": "portable-v3"
    }
    assert canonical._query_module().SEEN["kwargs"] == {
        "require_current_producer_identity": False,
        "allow_legacy_external_receipt": True,
    }


def test_canonical_query_preserves_legacy_portable_loader_interface(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    _use_portable_family(state)
    query_path = state.aoa_kag_root / "scripts" / "query_repo_local_kag.py"
    query_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.write_text(
        "SEEN = {}\n"
        "class RepoKagQuery:\n"
        "    def __init__(self, source_index, family):\n"
        "        self.source_index = source_index\n"
        "        SEEN['family'] = family\n"
        "    def discover(self):\n"
        "        return {'storage': self.source_index['storage']}\n"
        "def load_family(repo_root):\n"
        "    SEEN['loader_repo_root'] = repo_root\n"
        "    return {'storage': 'portable-v3'}, {}, None, None\n",
        encoding="utf-8",
    )

    canonical = CanonicalRepoKag(state)
    assert canonical.discover_owner("repo-a") == {"storage": "portable-v3"}
    module = canonical._query_module()
    assert module.SEEN["loader_repo_root"] == state.provider_root("repo-a")
    assert module.SEEN["family"] == {}


def test_canonical_query_bridges_pre_api_foreign_portable_observation(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    _use_portable_family(state)
    query_path = state.aoa_kag_root / "scripts" / "query_repo_local_kag.py"
    query_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.write_text(
        "from pathlib import Path\n"
        "SEEN = {}\n"
        "MANIFEST_RELATIVE_PATH = Path('kag/indexes/index_family.manifest.json')\n"
        "class RepoKagQuery:\n"
        "    def __init__(self, source_index, family):\n"
        "        self.source_index = source_index\n"
        "    def discover(self):\n"
        "        return {'storage': self.source_index['storage']}\n"
        "def load_family(repo_root, artifact_root=None, allow_shadow_git=True):\n"
        "    raise AssertionError('strict facade must not handle foreign v1')\n"
        "def load_portable_family_with_state(repo_root, **kwargs):\n"
        "    SEEN['kwargs'] = kwargs\n"
        "    return {'storage': 'portable-v3-bridge'}, {'entity': {'ok': True}}, {}, {'complete': True}\n"
        "def validate_repo_local_kag_repository_index_family(family, **kwargs):\n"
        "    SEEN['validation'] = kwargs\n"
        "    return family\n",
        encoding="utf-8",
    )

    canonical = CanonicalRepoKag(state)
    assert canonical.discover_owner("repo-a") == {
        "storage": "portable-v3-bridge"
    }
    module = canonical._query_module()
    assert module.SEEN["kwargs"] == {
        "require_current_producer_identity": False,
        "allow_legacy_external_receipt": True,
    }
    assert module.SEEN["validation"] == {
        "source_payload": {"storage": "portable-v3-bridge"},
        "label": "repo-a query family",
    }


def test_canonical_query_keeps_self_receipt_admission_strict(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    provider_map = state.provider_map()
    provider_map["providers"].append(
        {
            "repo": "aoa-kag",
            "provider_status": "provider_ready",
            "repo_local_index": {
                "source_index_ref": "kag/indexes/source_surface_index.json"
            },
        }
    )
    _write_json(state.provider_map_path, provider_map)
    _write_json(
        state.aoa_kag_root / "kag" / "indexes" / "source_surface_index.json",
        {"index_identity": {"content_digest": "self-source-fixture-digest"}},
    )
    query_path = state.aoa_kag_root / "scripts" / "query_repo_local_kag.py"
    query_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.write_text(
        "SEEN = {}\n"
        "class RepoKagQuery:\n"
        "    def __init__(self, source_index, family):\n"
        "        self.source_index = source_index\n"
        "    def discover(self):\n"
        "        return {'storage': self.source_index['storage']}\n"
        "def load_family(repo_root, **kwargs):\n"
        "    SEEN['kwargs'] = kwargs\n"
        "    return {'storage': 'self-v3'}, {}, None, None\n",
        encoding="utf-8",
    )

    canonical = CanonicalRepoKag(state)
    assert canonical.discover_owner("aoa-kag") == {"storage": "self-v3"}
    assert canonical._query_module().SEEN["kwargs"] == {
        "require_current_producer_identity": True,
        "allow_legacy_external_receipt": False,
    }


def test_canonical_query_passes_cold_cas_binding_to_owner_loader(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    _use_portable_family(state)
    artifact_root = tmp_path / "cold-cas"
    artifact_root.mkdir()
    state = AoAKagMCPState.discover(
        workspace_root=state.workspace_root,
        aoa_kag_root=state.aoa_kag_root,
        artifact_root=artifact_root,
    )
    query_path = state.aoa_kag_root / "scripts" / "query_repo_local_kag.py"
    query_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.write_text(
        "SEEN = {}\n"
        "class RepoKagQuery:\n"
        "    def __init__(self, source_index, family, repo_root=None):\n"
        "        self.source_index = source_index\n"
        "        SEEN['query_repo_root'] = repo_root\n"
        "    def discover(self):\n"
        "        return {'storage': self.source_index['storage']}\n"
        "def load_family(repo_root, **kwargs):\n"
        "    SEEN['loader_repo_root'] = repo_root\n"
        "    SEEN['kwargs'] = kwargs\n"
        "    return {'storage': 'portable-v4'}, {}, None, {'complete': True}\n",
        encoding="utf-8",
    )

    canonical = CanonicalRepoKag(state)
    assert canonical.discover_owner("repo-a") == {
        "storage": "portable-v4"
    }
    module = canonical._query_module()
    assert module.SEEN["loader_repo_root"] == state.provider_root("repo-a")
    assert module.SEEN["query_repo_root"] == state.provider_root("repo-a")
    assert module.SEEN["kwargs"] == {
        "require_current_producer_identity": False,
        "allow_legacy_external_receipt": True,
        "artifact_root": artifact_root.resolve(),
        "allow_shadow_git": False,
    }


def test_canonical_query_fails_closed_for_legacy_loader_with_artifact_binding(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    _use_portable_family(state)
    artifact_root = tmp_path / "cold-cas"
    artifact_root.mkdir()
    state = AoAKagMCPState.discover(
        workspace_root=state.workspace_root,
        aoa_kag_root=state.aoa_kag_root,
        artifact_root=artifact_root,
    )
    query_path = state.aoa_kag_root / "scripts" / "query_repo_local_kag.py"
    query_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.write_text(
        "class RepoKagQuery:\n"
        "    def __init__(self, source_index, family):\n"
        "        self.source_index = source_index\n"
        "    def discover(self):\n"
        "        return {'storage': self.source_index['storage']}\n"
        "def load_family(repo_root):\n"
        "    return {'storage': 'portable-v3'}, {}, None, None\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="requires the owner v4"):
        CanonicalRepoKag(state)._query("repo-a")


def test_server_exposes_compact_read_only_kag_surface(tmp_path: Path) -> None:
    state = _state(tmp_path)
    server = build_server(
        workspace_root=state.workspace_root,
        aoa_kag_root=state.aoa_kag_root,
        provider_map_path=state.provider_map_path,
        readiness_path=state.readiness_path,
        coverage_path=state.coverage_path,
        stack_root=tmp_path / "stack",
    )
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    resources = {str(resource.uri) for resource in asyncio.run(server.list_resources())}
    resource_templates = {
        str(resource.uri_template)
        for resource in asyncio.run(server.list_resource_templates())
    }

    assert server.application_version == "0.1.0"
    assert set(tools) == {
        "kag_discover",
        "kag_search",
        "kag_read",
        "kag_traverse",
        "kag_explain",
    }
    assert all(tool.output_schema for tool in tools.values())
    assert all(tool.annotations.read_only_hint is True for tool in tools.values())
    assert all(tool.annotations.destructive_hint is False for tool in tools.values())
    assert tools["kag_search"].input_schema["properties"]["limit"] == {
        "default": 10,
        "maximum": 10,
        "minimum": 1,
        "title": "Limit",
        "type": "integer",
    }
    assert tools["kag_traverse"].input_schema["properties"]["max_depth"] == {
        "default": 2,
        "maximum": 4,
        "minimum": 1,
        "title": "Max Depth",
        "type": "integer",
    }
    assert resources == {"aoa-kag://capabilities"}
    assert resource_templates == {
        "aoa-kag://owners/{repo}/manifest",
        "aoa-kag://records/{qualified_id}",
        "aoa-kag://documents/{document_id}",
        "aoa-kag://anchors/{anchor_id}",
        "aoa-kag://sources/{repo}/{document_id}",
        "aoa-kag://evidence/{trace_id}",
        "aoa-kag://schemas/{name}",
        "aoa-kag://projections/{digest}",
    }
    assert asyncio.run(server.list_prompts()) == []
