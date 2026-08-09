from __future__ import annotations

import asyncio
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
    cluster = {
        "cluster_id": "cluster:region:test",
        "cluster_kind": "region",
        "label": "Region: West Asia",
        "member_key": "properties.source_section",
        "member_value": "West Asia",
        "member_node_ids": ["atlas-row:A01", "dossier:A01"],
        "member_edge_ids": ["edge:row:A01:has-dossier:A01"],
        "view_ids": ["chronology"],
        "graph_layers": ["historical-relation"],
        "source_ref": "ToS/philosophy/graph-workbench/clusters/cluster-contracts.json",
        "source_refs": ["ToS/philosophy/atlas/master-tables/table-i/rows.jsonl"],
        "properties": {"review_use": "group by region"},
    }
    review_packet = {
        "packet_id": "review-packet:chronology",
        "view_id": "chronology",
        "review_intent": "Review chronology without canonizing dates.",
        "active_filters": {"node_types": ["atlas-row"]},
        "counts": {
            "nodes": 2,
            "edges": 1,
            "source_refs": 1,
            "clusters": 1,
            "weak_source_refs": 0,
            "unresolved_diagnostics": 0,
            "suspicious_dense_hubs": 0,
            "isolated_nodes": 0,
        },
        "layer_counts": [
            {"layer_id": "historical-relation", "node_count": 2, "edge_count": 1, "cluster_count": 1, "source_ref_count": 1}
        ],
        "cluster_summaries": [
            {
                "cluster_id": "cluster:region:test",
                "cluster_kind": "region",
                "label": "Region: West Asia",
                "node_count": 2,
                "edge_count": 1,
                "source_ref_count": 1,
            }
        ],
        "weak_source_refs": [],
        "unresolved_diagnostics": [],
        "suspicious_dense_hubs": [],
        "isolated_nodes": [],
        "candidate_to_canon_pressure": {"C": 1},
        "changed_subgraph": {"available": False, "reason": "test fixture"},
        "recommended_human_review_route": "ToS/philosophy/graph-workbench/views/chronology.graph.md",
        "source_refs": ["ToS/philosophy/atlas/master-tables/table-i/rows.jsonl"],
    }
    payload = {
        "schema_version": "tos_philosophy_graph_projection_v1",
        "owner_repo": "Tree-of-Sophia",
        "surface_kind": "derived_philosophy_graph_projection",
        "counts": {
            "views": 1,
            "graph_layers": 1,
            "nodes": 2,
            "edges": 1,
            "source_refs": 3,
            "clusters": 1,
            "review_packets": 1,
            "unresolved_review_surfaces": 0,
            "diagnostics": 0,
        },
        "visibility_model": {
            "default_payload_mode": "cluster-first",
            "default_depth": 1,
            "default_limit": 200,
            "layer_ids": ["historical-relation"],
            "expand_returns": ["member_node_ids", "member_edge_ids", "source_refs"],
            "cluster_contract_ref": "ToS/philosophy/graph-workbench/clusters/cluster-contracts.json",
            "review_packet_contract_ref": "ToS/philosophy/graph-workbench/review-packets/review-packet-contract.json",
            "lens_review_contract_ref": "ToS/philosophy/graph-workbench/views/lens-review-contracts.json",
        },
        "snapshot_review": {
            "snapshot_schema_version": "tos_philosophy_graph_projection_snapshot_v1",
            "current_snapshot": {
                "projection_fingerprint": "a" * 64,
                "count_fingerprint": "b" * 64,
                "view_fingerprints": [
                    {
                        "view_id": "chronology",
                        "fingerprint": "c" * 64,
                        "node_count": 2,
                        "edge_count": 1,
                        "cluster_count": 1,
                        "source_ref_count": 1,
                    }
                ],
            },
            "diff_route": {
                "mode": "fingerprint-ready",
                "changed_subgraph_available": False,
                "previous_snapshot_ref": None,
                "next_route": "compare against previous snapshot",
            },
        },
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
        "layer_counts": [
            {
                "layer_id": "historical-relation",
                "node_count": 2,
                "edge_count": 1,
                "view_count": 1,
                "cluster_count": 1,
                "source_ref_count": 3,
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
                "review_intent": "Review chronology without canonizing dates.",
                "source_posture": "Rows and clusters route back to source refs.",
                "evidence_posture": "Surface evidence before synthesis.",
                "collapse_rule": {"default_cluster_kinds": ["region"], "expand_to": ["rows", "source_refs"]},
                "ordering_hints": ["period"],
                "agent_packet_hint": "Bring chronology cluster and source refs.",
                "nodes": [node, neighbor],
                "edges": [edge],
                "source_refs": ["ToS/philosophy/atlas/master-tables/table-i/rows.jsonl"],
            }
        ],
        "nodes": [node, neighbor],
        "edges": [edge],
        "clusters": [cluster],
        "review_packets": [review_packet],
        "unresolved_review_surfaces": [],
    }
    projection_path.write_text(json.dumps(payload), encoding="utf-8")
    return projection_path


def write_post_planting_audit(root: Path) -> Path:
    audit_path = root / "ToS" / "philosophy" / "graph-workbench" / "review-packets" / "table-i-post-planting-audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "tos_philosophy_post_planting_audit_v1",
        "owner_repo": "Tree-of-Sophia",
        "counts": {"prepared_dossiers": 30, "errors": 0, "warnings": 0},
        "review_readiness": {"status": "ready_for_first_graph_review"},
    }
    audit_path.write_text(json.dumps(payload), encoding="utf-8")
    return audit_path


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
    server = build_server(tos_root=tmp_path)
    assert server is not None
    assert server._mcp_server.version == "0.2.0"


def test_published_tools_advertise_closed_world_read_only_contract(
    tmp_path: Path,
) -> None:
    write_index(tmp_path)
    server = build_server(tos_root=tmp_path)

    tools = asyncio.run(server.list_tools())

    assert tools
    for tool in tools:
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name
        assert tool.annotations.idempotent_hint is True, tool.name
        assert tool.annotations.open_world_hint is False, tool.name


def test_philosophy_graph_packets_and_resources(tmp_path: Path) -> None:
    write_index(tmp_path)
    write_philosophy_projection(tmp_path)
    write_post_planting_audit(tmp_path)
    state = state_for(tmp_path)

    status = state.philosophy_status()
    views = state.philosophy_views()
    contracts = state.philosophy_contracts()
    view = state.philosophy_view("chronology")
    layers = state.philosophy_layers()
    manifest = state.philosophy_scale_manifest(view_id="chronology", layers=["historical-relation"])
    clusters = state.philosophy_clusters(view_id="chronology")
    node = state.philosophy_node("atlas-row:A01")
    edge = state.philosophy_edge("edge:row:A01:has-dossier:A01")
    neighborhood = state.philosophy_neighborhood(
        "atlas-row:A01",
        layers=["historical-relation"],
        predicates=["has-dossier"],
    )
    path = state.philosophy_path_between(
        "atlas-row:A01",
        "dossier:A01",
        layers=["historical-relation"],
        predicates=["has-dossier"],
    )
    review = state.philosophy_review_packet("chronology")
    snapshot = state.philosophy_snapshot()
    audit = state.philosophy_audit()
    unresolved = state.philosophy_unresolved()
    lens = state.philosophy_lens_packet("chronology", limit=4)
    packet = state.philosophy_packet(query="dossier", view_id="chronology", limit=4)

    assert status["projection_exists"] is True
    assert status["counts"]["nodes"] == 2
    assert status["visibility_model"]["default_payload_mode"] == "cluster-first"
    assert views["views"][0]["layout_hint"] == "timeline-lanes"
    assert views["views"][0]["cluster_count"] == 1
    assert contracts["runtime_contract"]["source_owner"] == "Tree-of-Sophia"
    assert contracts["views"][0]["edge_predicates"] == ["has-dossier"]
    assert view["edge_count"] == 1
    assert view["clusters"][0]["cluster_kind"] == "region"
    assert layers["layer_counts"][0]["cluster_count"] == 1
    assert manifest["tables"]["nodes"]["row_count"] == 2
    assert manifest["tables"]["cluster-edge-memberships"]["row_count"] == 1
    assert clusters["cluster_count"] == 1
    assert node["related_edges"][0]["predicate_id"] == "has-dossier"
    assert node["source_refs"]
    assert edge["edge"]["to_id"] == "dossier:A01"
    assert neighborhood["neighbors"][0]["node_id"] == "dossier:A01"
    assert neighborhood["predicates"] == ["has-dossier"]
    assert neighborhood["source_refs"]
    assert path["found"] is True
    assert [item["node_id"] for item in path["nodes"]] == ["atlas-row:A01", "dossier:A01"]
    assert review["packet"]["packet_id"] == "review-packet:chronology"
    assert snapshot["snapshot_review"]["diff_route"]["mode"] == "fingerprint-ready"
    assert audit["audit"]["review_readiness"]["status"] == "ready_for_first_graph_review"
    assert unresolved["unresolved_count"] == 0
    assert lens["review_packet"]["view_id"] == "chronology"
    assert packet["result_count"] >= 1
    assert packet["view"]["clusters"][0]["cluster_id"] == "cluster:region:test"
    assert json.loads(state.render_resource("tos-philosophy://status"))["counts"]["edges"] == 1
    assert state.read_resource("tos-philosophy://view/chronology")["node_count"] == 2
    assert state.read_resource("tos-philosophy://layers")["layer_counts"][0]["cluster_count"] == 1
    assert state.read_resource("tos-philosophy://contracts")["views"][0]["view_id"] == "chronology"
    assert state.read_resource("tos-philosophy://scale-manifest")["tables"]["edges"]["row_count"] == 1
    assert state.read_resource("tos-philosophy://snapshot")["snapshot_review"]["diff_route"]["mode"] == "fingerprint-ready"
    assert state.read_resource("tos-philosophy://audit")["audit_exists"] is True
    assert state.read_resource("tos-philosophy://edge/edge:row:A01:has-dossier:A01")["edge"]["from_id"] == "atlas-row:A01"
    assert state.read_resource("tos-philosophy://review-packet/chronology")["packet"]["packet_id"] == "review-packet:chronology"
