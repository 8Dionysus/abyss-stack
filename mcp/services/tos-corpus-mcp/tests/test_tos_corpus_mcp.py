from __future__ import annotations

import json
from pathlib import Path

from tos_corpus_mcp.core import ToSCorpusMCPState
from tos_corpus_mcp.server import build_server


def write_index(root: Path) -> Path:
    index_path = root / "ToS" / "derived-exports" / "tos_corpus_index.min.json"
    index_path.parent.mkdir(parents=True)
    payload = {
        "schema_version": "tos_corpus_index_v1",
        "owner_repo": "Tree-of-Sophia",
        "surface_kind": "derived_corpus_index",
        "counts": {"branches": 1, "manifests": 1, "nodes": 1, "relation_packs": 1, "relation_edges": 1, "resources": 2},
        "authority_order": [{"layer": "canon", "owner_branch": "ToS/canon", "meaning": "reviewed authored nodes"}],
        "runtime_projection_boundary": {
            "runtime_owner": "abyss-stack",
            "allowed": ["serve MCP resources"],
            "not_allowed": ["be source truth"],
        },
        "graph_views": [
            {
                "view_id": "corpus-topology",
                "purpose": "show the corpus tree",
                "layout_hint": "elk-layered-or-graphviz-dot",
                "entry_surface": "ToS/source_home.manifest.json",
            },
            {
                "view_id": "route-graph",
                "purpose": "show relation packs",
                "layout_hint": "directed-route-graph",
                "entry_surface": "ToS/canon/relations",
            },
        ],
        "branches": [{"id": "canon", "path": "ToS/canon", "owner_surface": "ToS/canon/AGENTS.md", "authority_layer": "canon", "role": "canon"}],
        "manifests": [],
        "nodes": [
            {
                "node_id": "tos.concept.becoming",
                "node_type": "concept",
                "label": "becoming",
                "owner_branch": "ToS/canon",
                "authority_layer": "canon",
                "source_path": "ToS/canon/concept/becoming/node.json",
                "source_sha256": "0" * 64,
                "route_hint": None,
            }
        ],
        "relation_packs": [
            {
                "pack_id": "canon/relations/friedrich-nietzsche/thus-spoke-zarathustra/prologue-1",
                "path": "ToS/canon/relations/friedrich-nietzsche/thus-spoke-zarathustra/prologue-1/edges.csv",
                "route_hint": "relations/friedrich-nietzsche/thus-spoke-zarathustra/prologue-1",
                "owner_branch": "ToS/canon",
                "authority_layer": "canon",
                "edge_count": 1,
                "columns": ["edge_id", "from_id", "predicate_id", "to_id"],
                "sha256": "1" * 64,
            }
        ],
        "relation_edges": [
            {
                "edge_id": "m001",
                "pack_id": "canon/relations/friedrich-nietzsche/thus-spoke-zarathustra/prologue-1",
                "from_id": "tos.concept.becoming",
                "predicate_id": "parallel",
                "to_id": "tos.concept.overcoming",
                "owner_branch": "ToS/canon",
                "authority_layer": "canon",
                "layer": "source_linked",
                "status": "canon",
            }
        ],
        "resources": [
            {
                "path": "ToS/source_home.manifest.json",
                "resource_kind": "source_home_manifest",
                "owner_branch": "ToS",
                "authority_layer": "source_home",
                "sha256": "2" * 64,
                "size_bytes": 100,
            },
            {
                "path": "ToS/canon/concept/becoming/node.json",
                "resource_kind": "node_payload",
                "owner_branch": "ToS/canon",
                "authority_layer": "canon",
                "sha256": "0" * 64,
                "size_bytes": 120,
            },
        ],
        "diagnostics": [],
    }
    index_path.write_text(json.dumps(payload), encoding="utf-8")
    return index_path


def state_for(root: Path) -> ToSCorpusMCPState:
    return ToSCorpusMCPState.discover(tos_root=root)


def test_status_summary_and_search(tmp_path: Path) -> None:
    write_index(tmp_path)
    state = state_for(tmp_path)

    status = state.status()
    summary = state.summary()
    search = state.search("becoming")

    assert status["index_exists"] is True
    assert status["counts"]["nodes"] == 1
    assert summary["branches"][0]["id"] == "canon"
    assert search["result_count"] >= 1
    assert search["results"][0]["collection"] in {"nodes", "resources"}


def test_graph_view_node_relation_pack_and_resources(tmp_path: Path) -> None:
    write_index(tmp_path)
    state = state_for(tmp_path)

    view = state.graph_view("corpus-topology")
    node = state.node("tos.concept.becoming")
    pack = state.relation_pack("canon/relations/friedrich-nietzsche/thus-spoke-zarathustra/prologue-1")
    resources = state.resources(owner_branch="ToS/canon")

    assert view["view"]["layout_hint"] == "elk-layered-or-graphviz-dot"
    assert node["matches"][0]["node_type"] == "concept"
    assert pack["edges"][0]["edge_id"] == "m001"
    assert resources["resources"][0]["resource_kind"] == "node_payload"


def test_resources_and_server_build(tmp_path: Path) -> None:
    write_index(tmp_path)
    state = state_for(tmp_path)

    assert json.loads(state.render_resource("tos-corpus://status"))["counts"]["nodes"] == 1
    assert state.read_resource("tos-corpus://graph-view/corpus-topology")["item_count"] == 1
    assert build_server(tos_root=tmp_path) is not None
