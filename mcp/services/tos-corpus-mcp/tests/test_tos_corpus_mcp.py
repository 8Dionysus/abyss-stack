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


def write_philosophy_projection(root: Path) -> Path:
    projection_path = root / "ToS" / "derived-exports" / "philosophy_graph_projection.min.json"
    projection_path.parent.mkdir(parents=True, exist_ok=True)
    node = {
        "node_id": "atlas-row:A01",
        "label": "A01",
        "node_type": "atlas-row",
        "graph_layers": ["historical-relation"],
        "view_ids": ["chronology"],
        "source_ref": "ToS/philosophy/atlas/master-tables/table-i/rows.jsonl",
        "properties": {},
    }
    neighbor = {
        "node_id": "dossier:A01",
        "label": "A01 dossier",
        "node_type": "dossier",
        "graph_layers": ["historical-relation"],
        "view_ids": ["chronology"],
        "source_ref": "ToS/philosophy/dossiers/A01.md",
        "properties": {},
    }
    edge = {
        "edge_id": "edge:row:A01:has-dossier:A01",
        "from_id": "atlas-row:A01",
        "to_id": "dossier:A01",
        "predicate_id": "has-dossier",
        "graph_layers": ["historical-relation"],
        "view_ids": ["chronology"],
        "source_ref": "ToS/philosophy/atlas/master-tables/table-i/edges.csv",
        "properties": {},
    }
    payload = {
        "schema_version": "tos_philosophy_graph_projection_v1",
        "owner_repo": "Tree-of-Sophia",
        "surface_kind": "derived_philosophy_graph_projection",
        "counts": {"views": 1, "graph_layers": 1, "nodes": 2, "edges": 1, "source_refs": 3, "diagnostics": 0},
        "runtime_projection_boundary": {
            "runtime_owner": "abyss-stack",
            "runtime_scope": ["serve MCP packets"],
            "tos_authority_scope": ["own source_refs"],
        },
        "graph_layers": [
            {
                "layer_id": "historical-relation",
                "use": "chronological branch relation",
                "source_ref": "ToS/philosophy/trunk/graph-layers/README.md",
            }
        ],
        "views": [
            {
                "view_id": "chronology",
                "title": "Chronology",
                "source_ref": "ToS/philosophy/graph-workbench/views/chronology.graph.md",
                "route_card": "ToS/philosophy/graph-workbench/views/AGENTS.md",
                "layout_hint": "timeline-lanes",
                "graph_layers": ["historical-relation"],
                "nodes": [node, neighbor],
                "edges": [edge],
                "source_refs": ["ToS/philosophy/atlas/master-tables/table-i/rows.jsonl"],
            }
        ],
        "nodes": [node, neighbor],
        "edges": [edge],
    }
    projection_path.write_text(json.dumps(payload), encoding="utf-8")
    return projection_path


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


def test_philosophy_graph_packets_and_resources(tmp_path: Path) -> None:
    write_index(tmp_path)
    write_philosophy_projection(tmp_path)
    state = state_for(tmp_path)

    status = state.philosophy_status()
    views = state.philosophy_views()
    view = state.philosophy_view("chronology")
    node = state.philosophy_node("atlas-row:A01")
    neighborhood = state.philosophy_neighborhood("atlas-row:A01")
    packet = state.philosophy_packet(query="dossier", view_id="chronology", limit=4)

    assert status["projection_exists"] is True
    assert status["counts"]["nodes"] == 2
    assert views["views"][0]["layout_hint"] == "timeline-lanes"
    assert view["edge_count"] == 1
    assert node["related_edges"][0]["predicate_id"] == "has-dossier"
    assert neighborhood["neighbors"][0]["node_id"] == "dossier:A01"
    assert packet["result_count"] >= 1
    assert json.loads(state.render_resource("tos-philosophy://status"))["counts"]["edges"] == 1
    assert state.read_resource("tos-philosophy://view/chronology")["node_count"] == 2
