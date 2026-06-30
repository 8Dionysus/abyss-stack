from __future__ import annotations

import csv
import json
import sys
from copy import deepcopy
from io import StringIO
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "config-templates" / "Services" / "tos-graph"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import TosGraphSettings, load_settings  # noqa: E402
from app.corpus_reader import ToSCorpusReader  # noqa: E402
from app.neo4j_store import Neo4jProjectionStore, Neo4jStoreStatus  # noqa: E402
from app.philosophy_reader import ToSPhilosophyProjectionReader  # noqa: E402
from app.projector import CorpusProjector, PhilosophyProjector  # noqa: E402


def write_index(root: Path) -> Path:
    index_path = root / "ToS" / "derived-exports" / "tos_corpus_index.min.json"
    index_path.parent.mkdir(parents=True)
    payload = {
        "schema_version": "tos_corpus_index_v1",
        "schema_ref": "ToS/contracts/tos-corpus-index.schema.json",
        "owner_repo": "Tree-of-Sophia",
        "surface_kind": "derived_corpus_index",
        "counts": {"branches": 1, "manifests": 1, "nodes": 1, "relation_packs": 1, "relation_edges": 1, "resources": 2},
        "authority_order": [{"layer": "canon", "owner_branch": "ToS/canon", "meaning": "reviewed authored nodes"}],
        "runtime_projection_boundary": {
            "runtime_owner": "abyss-stack",
            "allowed": ["serve graph UI"],
            "not_allowed": ["be source truth"],
        },
        "graph_views": [
            {
                "view_id": "corpus-topology",
                "purpose": "show the corpus tree",
                "layout_hint": "elk-layered-or-graphviz-dot",
                "entry_surface": "ToS/source_home.manifest.json",
            }
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
                "pack_id": "canon/relations/demo",
                "path": "ToS/canon/relations/demo/edges.csv",
                "route_hint": "relations/demo",
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
                "pack_id": "canon/relations/demo",
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

    def multilingual_label(original: str | None, ru: str, en: str, source_ref: str) -> dict[str, object]:
        return {
            "schema_version": "tos_multilingual_label_v1",
            "label": {
                "original": original,
                "ru": ru,
                "en": en,
            },
            "language": {
                "original_language": None,
                "original_script": None,
                "transliteration": None,
            },
            "translation_status": {
                "original": "source" if original else "pending",
                "ru": "reviewed",
                "en": "reviewed",
            },
            "source_ref": source_ref,
        }

    node_a = {
        "node_id": "atlas-row:A01",
        "label": "A01",
        "multilingual": multilingual_label(
            None,
            "A01 — Протоклинопись и учётные онтологии",
            "A01 — Proto-Cuneiform and Accounting Ontologies",
            "ToS/philosophy/atlas/master-tables/table-i/rows.jsonl",
        ),
        "node_type": "atlas-row",
        "graph_layers": ["historical-relation"],
        "view_ids": ["chronology"],
        "source_ref": "ToS/philosophy/atlas/master-tables/table-i/rows.jsonl",
        "properties": {"period": "early writing"},
    }
    node_b = {
        "node_id": "dossier:A01",
        "label": "A01 dossier",
        "multilingual": multilingual_label(
            None,
            "Досье A01",
            "A01 dossier",
            "ToS/philosophy/dossiers/A01.md",
        ),
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
        "multilingual": multilingual_label(
            None,
            "Регион: Западная Азия",
            "Region: West Asia",
            "ToS/philosophy/graph-workbench/clusters/cluster-contracts.json",
        ),
        "member_key": "properties.source_section",
        "member_value": "West Asia",
        "member_node_ids": ["atlas-row:A01", "dossier:A01"],
        "member_edge_ids": ["edge:row:A01:has-dossier:A01"],
        "view_ids": ["chronology"],
        "graph_layers": ["historical-relation"],
        "source_ref": "ToS/philosophy/graph-workbench/clusters/cluster-contracts.json",
        "source_refs": [
            "ToS/philosophy/atlas/master-tables/table-i/rows.jsonl",
            "ToS/philosophy/dossiers/A01.md",
        ],
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
            "source_refs": 2,
            "clusters": 1,
            "weak_source_refs": 0,
            "unresolved_diagnostics": 0,
            "suspicious_dense_hubs": 0,
            "isolated_nodes": 0,
        },
        "layer_counts": [
            {
                "layer_id": "historical-relation",
                "node_count": 2,
                "edge_count": 1,
                "cluster_count": 1,
                "source_ref_count": 2,
            }
        ],
        "cluster_summaries": [
            {
                "cluster_id": "cluster:region:test",
                "cluster_kind": "region",
                "label": "Region: West Asia",
                "node_count": 2,
                "edge_count": 1,
                "source_ref_count": 2,
            }
        ],
        "weak_source_refs": [],
        "unresolved_diagnostics": [],
        "suspicious_dense_hubs": [],
        "isolated_nodes": [],
        "candidate_to_canon_pressure": {"C": 1},
        "changed_subgraph": {"available": False, "reason": "test fixture"},
        "recommended_human_review_route": "ToS/philosophy/graph-workbench/views/chronology.graph.md",
        "source_refs": [
            "ToS/philosophy/atlas/master-tables/table-i/rows.jsonl",
            "ToS/philosophy/atlas/master-tables/table-i/edges.csv",
        ],
    }
    payload = {
        "schema_version": "tos_philosophy_graph_projection_v1",
        "schema_ref": "ToS/contracts/philosophy-graph-projection.schema.json",
        "owner_repo": "Tree-of-Sophia",
        "surface_kind": "derived_philosophy_graph_projection",
        "source_refs": {
            "atlas_projection_ref": "ToS/derived-exports/philosophy_atlas_projection.min.json",
            "graph_view_catalog_ref": "ToS/derived-exports/philosophy_graph_views.min.json",
            "source_view_contract_ref": "ToS/philosophy/graph-workbench/views/view-contracts.json",
            "lens_review_contract_ref": "ToS/philosophy/graph-workbench/views/lens-review-contracts.json",
            "cluster_contract_ref": "ToS/philosophy/graph-workbench/clusters/cluster-contracts.json",
            "review_packet_contract_ref": "ToS/philosophy/graph-workbench/review-packets/review-packet-contract.json",
        },
        "content_language_contract": {
            "schema_version": "tos_multilingual_content_contract_v1",
            "source_ref": "ToS/philosophy/atlas/multilingual/content-labels.json",
            "display_languages": ["original", "ru", "en"],
            "required_translation_languages": ["ru", "en"],
            "original_language_rule": "preserve attested original titles or mark pending",
            "downstream_consumer_rule": "abyss-stack reads generated multilingual fields",
        },
        "runtime_projection_boundary": {
            "runtime_owner": "abyss-stack",
            "runtime_scope": ["serve projection"],
            "tos_authority_scope": ["own source_refs"],
        },
        "validation_refs": ["scripts/build_philosophy_graph_projection.py"],
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
                        "source_ref_count": 2,
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
                "order": 10,
                "layout_hint": "timeline-lanes",
                "graph_layers": ["historical-relation"],
                "filters_applied": {"node_types": ["atlas-row"]},
                "future_branch_filters": {},
                "review_intent": "Review chronology without canonizing dates.",
                "source_posture": "Rows and clusters route back to source refs.",
                "evidence_posture": "Surface evidence before synthesis.",
                "collapse_rule": {"default_cluster_kinds": ["region"], "expand_to": ["rows", "source_refs"]},
                "ordering_hints": ["period"],
                "agent_packet_hint": "Bring chronology cluster and source refs.",
                "nodes": [node_a, node_b],
                "edges": [edge],
                "source_refs": [
                    "ToS/philosophy/atlas/master-tables/table-i/rows.jsonl",
                    "ToS/philosophy/atlas/master-tables/table-i/edges.csv",
                ],
                "diagnostics": [],
            }
        ],
        "nodes": [node_a, node_b],
        "edges": [edge],
        "clusters": [cluster],
        "review_packets": [review_packet],
        "unresolved_review_surfaces": [],
        "diagnostics": [],
    }
    projection_path.write_text(json.dumps(payload), encoding="utf-8")
    return projection_path


def write_multiview_philosophy_projection(root: Path) -> Path:
    projection_path = write_philosophy_projection(root)
    payload = json.loads(projection_path.read_text(encoding="utf-8"))
    transmission_node = {
        "node_id": "transmission:A01",
        "label": "A01 transmission channel",
        "node_type": "transmission-node",
        "graph_layers": ["transmission-relation"],
        "view_ids": ["transmission"],
        "source_ref": "ToS/philosophy/atlas/dossiers/transmission-backlog.jsonl",
        "properties": {"channel": "school archive"},
    }
    transmission_edge = {
        "edge_id": "edge:dossier:A01:transmits:A01",
        "from_id": "dossier:A01",
        "to_id": "transmission:A01",
        "predicate_id": "transmits_to",
        "graph_layers": ["transmission-relation"],
        "view_ids": ["transmission"],
        "source_ref": "ToS/philosophy/graph-workbench/proposed-relations/table-i-prepared-dossiers.jsonl",
        "properties": {},
    }
    transmission_cluster = {
        "cluster_id": "cluster:transmission:test",
        "cluster_kind": "transmission",
        "label": "Transmission: school archive",
        "member_node_ids": ["dossier:A01", "transmission:A01"],
        "member_edge_ids": ["edge:dossier:A01:transmits:A01"],
        "view_ids": ["transmission"],
        "graph_layers": ["transmission-relation"],
        "source_ref": "ToS/philosophy/graph-workbench/clusters/cluster-contracts.json",
        "source_refs": [
            "ToS/philosophy/atlas/dossiers/transmission-backlog.jsonl",
            "ToS/philosophy/graph-workbench/proposed-relations/table-i-prepared-dossiers.jsonl",
        ],
        "properties": {"review_use": "group by transmission route"},
    }
    transmission_packet = deepcopy(payload["review_packets"][0])
    transmission_packet.update(
        {
            "packet_id": "review-packet:transmission",
            "view_id": "transmission",
            "review_intent": "Review transmission routes without canonizing influence.",
            "recommended_human_review_route": "ToS/philosophy/graph-workbench/views/transmission.graph.md",
        }
    )
    transmission_packet["counts"] = {
        **transmission_packet["counts"],
        "nodes": 2,
        "edges": 1,
        "clusters": 1,
    }
    transmission_packet["layer_counts"] = [
        {
            "layer_id": "transmission-relation",
            "node_count": 2,
            "edge_count": 1,
            "cluster_count": 1,
            "source_ref_count": 2,
        }
    ]
    transmission_view = {
        "view_id": "transmission",
        "title": "Transmission",
        "source_ref": "ToS/philosophy/graph-workbench/views/transmission.graph.md",
        "route_card": "ToS/philosophy/graph-workbench/views/AGENTS.md",
        "order": 20,
        "layout_hint": "directed-corridors",
        "graph_layers": ["transmission-relation"],
        "filters_applied": {"relation_kinds": ["transmits_to"]},
        "future_branch_filters": {},
        "review_intent": "Review transmission routes without canonizing influence.",
        "source_posture": "Transmission rows route back to source refs.",
        "evidence_posture": "Surface route pressure before synthesis.",
        "collapse_rule": {"default_cluster_kinds": ["transmission"], "expand_to": ["rows", "source_refs"]},
        "ordering_hints": ["route"],
        "agent_packet_hint": "Bring transmission cluster and source refs.",
        "nodes": [payload["nodes"][1], transmission_node],
        "edges": [transmission_edge],
        "source_refs": [
            "ToS/philosophy/atlas/dossiers/transmission-backlog.jsonl",
            "ToS/philosophy/graph-workbench/proposed-relations/table-i-prepared-dossiers.jsonl",
        ],
        "diagnostics": [],
    }
    payload["views"].append(transmission_view)
    payload["nodes"].append(transmission_node)
    payload["edges"].append(transmission_edge)
    payload["clusters"].append(transmission_cluster)
    payload["review_packets"].append(transmission_packet)
    payload["graph_layers"].append(
        {
            "layer_id": "transmission-relation",
            "use": "transmission route relation",
            "source_ref": "ToS/philosophy/trunk/graph-layers/README.md",
        }
    )
    payload["layer_counts"].append(
        {
            "layer_id": "transmission-relation",
            "node_count": 2,
            "edge_count": 1,
            "view_count": 1,
            "cluster_count": 1,
            "source_ref_count": 2,
        }
    )
    payload["counts"].update(
        {
            "views": 2,
            "graph_layers": 2,
            "nodes": 3,
            "edges": 2,
            "source_refs": 5,
            "clusters": 2,
            "review_packets": 2,
        }
    )
    payload["visibility_model"]["layer_ids"].append("transmission-relation")
    payload["snapshot_review"]["current_snapshot"]["view_fingerprints"].append(
        {
            "view_id": "transmission",
            "fingerprint": "d" * 64,
            "node_count": 2,
            "edge_count": 1,
            "cluster_count": 1,
            "source_ref_count": 2,
        }
    )
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
        "graph_projection_audit": {"snapshot_ready": True, "views": 1, "review_packets": 1},
    }
    audit_path.write_text(json.dumps(payload), encoding="utf-8")
    return audit_path


def settings_for(root: Path) -> TosGraphSettings:
    return TosGraphSettings(
        service_name="tos-graph",
        port=5410,
        config_path=root / "config.yaml",
        stack_env_path=root / "stack.env",
        tos_root=root,
        log_root=root / "logs",
        corpus_index_path=root / "ToS" / "derived-exports" / "tos_corpus_index.min.json",
        philosophy_atlas_projection_path=root / "ToS" / "derived-exports" / "philosophy_atlas_projection.min.json",
        philosophy_graph_views_path=root / "ToS" / "derived-exports" / "philosophy_graph_views.min.json",
        philosophy_graph_projection_path=root / "ToS" / "derived-exports" / "philosophy_graph_projection.min.json",
        philosophy_post_planting_audit_path=root
        / "ToS"
        / "philosophy"
        / "graph-workbench"
        / "review-packets"
        / "table-i-post-planting-audit.json",
        default_view="corpus-topology",
        default_philosophy_view="chronology",
        write_enabled=False,
        neo4j_uri=None,
        neo4j_user=None,
        neo4j_password=None,
        neo4j_database="neo4j",
        projection_mode="corpus_sync",
    )


def test_corpus_reader_exposes_graph_views_and_search(tmp_path: Path) -> None:
    write_index(tmp_path)
    reader = ToSCorpusReader(settings_for(tmp_path))

    status = reader.status()
    view = reader.graph_view("corpus-topology")
    search = reader.search("becoming")

    assert status["index_exists"] is True
    assert status["counts"]["nodes"] == 1
    assert view["item_count"] == 1
    assert search["result_count"] >= 1


def test_corpus_projection_preview_uses_whole_index_counts(tmp_path: Path) -> None:
    write_index(tmp_path)
    settings = settings_for(tmp_path)
    reader = ToSCorpusReader(settings)
    status = Neo4jStoreStatus(
        configured=False,
        ready=False,
        uri=None,
        user=None,
        database="neo4j",
        projection_mode="corpus_sync",
        note="preview",
    )
    projector = CorpusProjector(reader, status, Neo4jProjectionStore(settings, status))

    result = projector.sync_corpus()

    assert result["surface"] == "ToS/derived-exports/tos_corpus_index.min.json"
    assert result["status"] == "preview_only"
    assert result["node_count"] == 1
    assert result["edge_count"] == 1
    assert result["resource_count"] == 2


def test_corpus_relation_edge_projection_ids_include_pack_id() -> None:
    rows = Neo4jProjectionStore._corpus_rows(
        {
            "relation_edges": [
                {"pack_id": "canon/relations/a", "edge_id": "m001", "from_id": "a", "to_id": "b"},
                {"pack_id": "canon/relations/b", "edge_id": "m001", "from_id": "c", "to_id": "d"},
            ]
        },
        "relation_edges",
    )

    assert [row["id"] for row in rows] == ["canon/relations/a::m001", "canon/relations/b::m001"]


def test_philosophy_reader_exposes_views_nodes_and_neighborhood(tmp_path: Path) -> None:
    write_philosophy_projection(tmp_path)
    write_post_planting_audit(tmp_path)
    reader = ToSPhilosophyProjectionReader(settings_for(tmp_path))

    status = reader.status()
    views = reader.views()
    view = reader.view("chronology")
    node = reader.node("atlas-row:A01")
    neighborhood = reader.neighborhood("atlas-row:A01", depth=1, layers={"historical-relation"})
    filtered_neighborhood = reader.neighborhood(
        "atlas-row:A01",
        depth=1,
        layers={"historical-relation"},
        predicates={"missing-predicate"},
    )
    layers = reader.layers()
    clusters = reader.clusters(view_id="chronology")
    review_packet = reader.review_packet("chronology")
    snapshot = reader.snapshot()
    audit = reader.audit()
    edge = reader.edge("edge:row:A01:has-dossier:A01")
    unresolved = reader.unresolved()
    path = reader.path_between("atlas-row:A01", "dossier:A01", layers={"historical-relation"})
    filtered_path = reader.path_between(
        "atlas-row:A01",
        "dossier:A01",
        layers={"historical-relation"},
        predicates={"missing-predicate"},
    )
    query_view = reader.query_view(
        "chronology",
        layers={"historical-relation"},
        predicates={"has-dossier"},
        query_backend="json-fallback",
        fallback_reason="neo4j unavailable in test",
    )

    assert status["projection_exists"] is True
    assert status["counts"]["nodes"] == 2
    assert status["visibility_model"]["default_payload_mode"] == "cluster-first"
    assert views["views"][0]["layout_hint"] == "timeline-lanes"
    assert views["views"][0]["cluster_count"] == 1
    assert view["node_count"] == 2
    assert view["edge_count"] == 1
    assert view["clusters"][0]["cluster_kind"] == "region"
    assert node["node"]["source_ref"].endswith("rows.jsonl")
    assert neighborhood["neighbors"][0]["node_id"] == "dossier:A01"
    assert neighborhood["query_backend"] == "json"
    assert filtered_neighborhood["neighbors"] == []
    assert layers["layer_counts"][0]["cluster_count"] == 1
    assert clusters["cluster_count"] == 1
    assert review_packet["packet"]["packet_id"] == "review-packet:chronology"
    assert snapshot["snapshot_review"]["diff_route"]["mode"] == "fingerprint-ready"
    assert audit["audit"]["review_readiness"]["status"] == "ready_for_first_graph_review"
    assert edge["edge"]["from_id"] == "atlas-row:A01"
    assert [item["node_id"] for item in edge["endpoints"]] == ["atlas-row:A01", "dossier:A01"]
    assert unresolved["unresolved_count"] == 0
    assert path["found"] is True
    assert [item["node_id"] for item in path["nodes"]] == ["atlas-row:A01", "dossier:A01"]
    assert path["query_backend"] == "json"
    assert filtered_path["found"] is False
    assert query_view["query_backend"] == "json-fallback"
    assert query_view["fallback_reason"] == "neo4j unavailable in test"
    assert query_view["query_contract"]["query_kind"] == "view-subgraph"
    assert query_view["edge_count"] == 1


def test_philosophy_reader_exposes_scale_export_tables(tmp_path: Path) -> None:
    write_philosophy_projection(tmp_path)
    reader = ToSPhilosophyProjectionReader(settings_for(tmp_path))

    manifest = reader.scale_export_manifest(view_id="chronology", layers={"historical-relation"})
    nodes = reader.scale_export_table("nodes", view_id="chronology", layers={"historical-relation"})
    edges = reader.scale_export_table("edges", view_id="chronology", layers={"historical-relation"})
    clusters = reader.scale_export_table("clusters", view_id="chronology", layers={"historical-relation"})
    cluster_nodes = reader.scale_export_table(
        "cluster-node-memberships",
        view_id="chronology",
        layers={"historical-relation"},
    )
    cluster_edges = reader.scale_export_table(
        "cluster-edge-memberships",
        view_id="chronology",
        layers={"historical-relation"},
    )

    assert manifest["schema"] == "tos_graph_philosophy_scale_export_manifest_v1"
    assert manifest["tables"]["nodes"]["row_count"] == 2
    assert "label_ru" in manifest["tables"]["nodes"]["columns"]
    assert "label_en" in manifest["tables"]["clusters"]["columns"]
    assert manifest["tables"]["edges"]["formats"] == ["csv", "jsonl"]
    assert nodes[0]["id"] == "atlas-row:A01"
    assert nodes[0]["label_ru"] == "A01 — Протоклинопись и учётные онтологии"
    assert nodes[0]["label_en"] == "A01 — Proto-Cuneiform and Accounting Ontologies"
    assert nodes[0]["graph_layers"] == "historical-relation"
    assert json.loads(nodes[0]["source_refs"]) == ["ToS/philosophy/atlas/master-tables/table-i/rows.jsonl"]
    assert edges[0]["source"] == "atlas-row:A01"
    assert edges[0]["target"] == "dossier:A01"
    assert edges[0]["predicate"] == "has-dossier"
    assert clusters[0]["id"] == "cluster:region:test"
    assert clusters[0]["label_ru"] == "Регион: Западная Азия"
    assert clusters[0]["label_en"] == "Region: West Asia"
    assert clusters[0]["member_count"] == "2"
    assert cluster_nodes[0]["cluster_id"] == "cluster:region:test"
    assert cluster_nodes[0]["node_id"] == "atlas-row:A01"
    assert cluster_edges[0]["edge_id"] == "edge:row:A01:has-dossier:A01"

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=manifest["tables"]["edges"]["columns"], extrasaction="ignore")
    writer.writeheader()
    writer.writerows(edges)
    parsed_edges = list(csv.DictReader(StringIO(output.getvalue())))
    assert parsed_edges[0]["source"] == "atlas-row:A01"
    assert parsed_edges[0]["target"] == "dossier:A01"


def test_philosophy_reader_exposes_distinct_view_subgraph_contracts(tmp_path: Path) -> None:
    write_multiview_philosophy_projection(tmp_path)
    reader = ToSPhilosophyProjectionReader(settings_for(tmp_path))

    chronology = reader.view("chronology")
    transmission = reader.view("transmission")
    contracts = reader.contracts()
    chronology_export = reader.scale_export_bundle(view_id="chronology")
    transmission_export = reader.scale_export_bundle(view_id="transmission")

    chronology_nodes = {node["node_id"] for node in chronology["nodes"]}
    transmission_nodes = {node["node_id"] for node in transmission["nodes"]}
    chronology_edges = {edge["edge_id"] for edge in chronology["edges"]}
    transmission_edges = {edge["edge_id"] for edge in transmission["edges"]}

    assert chronology_nodes != transmission_nodes
    assert chronology_edges != transmission_edges
    assert chronology["subgraph_contract"]["graph_layers"] == ["historical-relation"]
    assert transmission["subgraph_contract"]["graph_layers"] == ["transmission-relation"]
    assert transmission["subgraph_contract"]["edge_predicates"] == ["transmits_to"]
    assert chronology_export["row_counts"]["nodes"] == 2
    assert transmission_export["row_counts"]["nodes"] == 2
    assert chronology_export["tables"]["edges"][0]["predicate"] == "has-dossier"
    assert transmission_export["tables"]["edges"][0]["predicate"] == "transmits_to"
    assert contracts["schema"] == "tos_graph_philosophy_contracts_v1"
    assert {view["view_id"] for view in contracts["views"]} == {"chronology", "transmission"}
    assert "source_view_contract_ref" in contracts["source_contract_refs"]
    assert contracts["runtime_contract"]["source_owner"] == "Tree-of-Sophia"


def test_philosophy_projection_preview_uses_projection_counts(tmp_path: Path) -> None:
    write_philosophy_projection(tmp_path)
    settings = settings_for(tmp_path)
    reader = ToSPhilosophyProjectionReader(settings)
    status = Neo4jStoreStatus(
        configured=False,
        ready=False,
        uri=None,
        user=None,
        database="neo4j",
        projection_mode="corpus_and_philosophy_sync",
        note="preview",
    )
    projector = PhilosophyProjector(reader, status, Neo4jProjectionStore(settings, status))

    result = projector.sync_philosophy()

    assert result["surface"] == "ToS/derived-exports/philosophy_graph_projection.min.json"
    assert result["status"] == "preview_only"
    assert result["node_count"] == 2
    assert result["edge_count"] == 1
    assert result["resource_count"] == 3
    assert result["branch_count"] == 1
    assert result["constraint_count"] is None
    assert result["scale_export_row_counts"]["nodes"] == 2


def test_philosophy_neo4j_rows_keep_payload_json_and_membership_shape(tmp_path: Path) -> None:
    projection_path = write_philosophy_projection(tmp_path)
    projection = json.loads(projection_path.read_text(encoding="utf-8"))

    node_rows = Neo4jProjectionStore._philosophy_rows(projection, "nodes", "node_id")
    edge_rows = Neo4jProjectionStore._philosophy_rows(projection, "edges", "edge_id")
    cluster_rows = Neo4jProjectionStore._philosophy_rows(projection, "clusters", "cluster_id")
    review_packet_rows = Neo4jProjectionStore._philosophy_rows(projection, "review_packets", "packet_id")
    source_rows = Neo4jProjectionStore._philosophy_source_rows(projection)

    assert node_rows[0]["id"] == "atlas-row:A01"
    assert json.loads(node_rows[0]["props"]["payload_json"])["properties"]["period"] == "early writing"
    assert node_rows[0]["graph_layers"] == ["historical-relation"]
    assert edge_rows[0]["from_id"] == "atlas-row:A01"
    assert edge_rows[0]["to_id"] == "dossier:A01"
    assert cluster_rows[0]["member_node_ids"] == ["atlas-row:A01", "dossier:A01"]
    assert cluster_rows[0]["source_refs"]
    assert review_packet_rows[0]["view_id"] == "chronology"
    assert any(row["id"].endswith("view-contracts.json") for row in source_rows)
    assert any(row["id"].endswith("cluster-contracts.json") for row in source_rows)


class RecordingResult:
    def __init__(self, record: dict[str, object] | None = None, rows: list[dict[str, object]] | None = None) -> None:
        self.record = record
        self.rows = rows or []

    def single(self) -> dict[str, object] | None:
        return self.record

    def data(self) -> list[dict[str, object]]:
        return self.rows

    def consume(self) -> None:
        return None


class RecordingTx:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.params: list[dict[str, object]] = []

    def run(self, query: str, **params: object) -> RecordingResult:
        self.queries.append(" ".join(query.split()))
        self.params.append(params)
        if "deleted_node_count" in query:
            return RecordingResult({"deleted_node_count": 8, "deleted_edge_count": 13})
        return RecordingResult()


def test_philosophy_neo4j_refresh_uses_constraints_refresh_ids_and_stale_cleanup(tmp_path: Path) -> None:
    projection_path = write_philosophy_projection(tmp_path)
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    node_rows = Neo4jProjectionStore._philosophy_rows(projection, "nodes", "node_id")
    edge_rows = Neo4jProjectionStore._philosophy_rows(projection, "edges", "edge_id")
    cluster_rows = Neo4jProjectionStore._philosophy_rows(projection, "clusters", "cluster_id")

    refresh_id = "tos-philosophy:test-refresh"
    constraint_tx = RecordingTx()
    data_tx = RecordingTx()
    cleanup_tx = RecordingTx()
    constraint_count = Neo4jProjectionStore._ensure_philosophy_constraints(constraint_tx)
    Neo4jProjectionStore._merge_philosophy_rows(
        data_tx,
        "TosPhilosophyNodeProjection",
        "PROJECTS_NODE",
        node_rows,
        refresh_id,
    )
    Neo4jProjectionStore._link_philosophy_view_nodes(data_tx, node_rows, refresh_id)
    Neo4jProjectionStore._link_philosophy_layer_memberships(
        data_tx,
        "TosPhilosophyNodeProjection",
        node_rows,
        refresh_id,
    )
    Neo4jProjectionStore._link_philosophy_source_refs(data_tx, "TosPhilosophyNodeProjection", node_rows, refresh_id)
    Neo4jProjectionStore._link_philosophy_cluster_members(data_tx, cluster_rows, refresh_id)
    Neo4jProjectionStore._link_philosophy_edges(data_tx, edge_rows, refresh_id)
    deleted_counts = Neo4jProjectionStore._delete_stale_philosophy_projection(cleanup_tx, refresh_id)

    assert constraint_count == 8
    assert all("CREATE CONSTRAINT" in query and "IF NOT EXISTS" in query for query in constraint_tx.queries)
    assert any("TosPhilosophyNodeProjection" in query for query in constraint_tx.queries)
    assert deleted_counts == {"deleted_node_count": 8, "deleted_edge_count": 13}
    assert any("MERGE (projection:TosPhilosophyNodeProjection" in query for query in data_tx.queries)
    assert any("SET projection.refresh_id = $refresh_id" in query for query in data_tx.queries)
    assert any("MERGE (cluster)-[rel:CLUSTERS_NODE]->(node)" in query for query in data_tx.queries)
    assert any("MERGE (source)-[rel:TOS_PHILOSOPHY_RELATION" in query for query in data_tx.queries)
    assert cleanup_tx.queries[0].startswith("MATCH ()-[rel]-() WHERE type(rel) IN $relation_types")
    assert cleanup_tx.params[0]["refresh_id"] == refresh_id


def test_philosophy_neo4j_view_query_tx_returns_projection_packet(tmp_path: Path) -> None:
    projection_path = write_philosophy_projection(tmp_path)
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    view = projection["views"][0]
    node = projection["nodes"][0]
    edge = projection["edges"][0]
    cluster = projection["clusters"][0]
    boundary = projection["runtime_projection_boundary"]

    class QueryTx(RecordingTx):
        def run(self, query: str, **params: object) -> RecordingResult:
            self.queries.append(" ".join(query.split()))
            self.params.append(params)
            compact_query = self.queries[-1]
            if "RETURN view.payload_json AS payload_json" in compact_query:
                return RecordingResult({"payload_json": json.dumps(view)})
            if "RETURN node.payload_json AS payload_json" in compact_query:
                return RecordingResult(rows=[{"payload_json": json.dumps(node)}])
            if "RETURN edge.payload_json AS payload_json" in compact_query:
                return RecordingResult(rows=[{"payload_json": json.dumps(edge)}])
            if "RETURN cluster.payload_json AS payload_json" in compact_query:
                return RecordingResult(rows=[{"payload_json": json.dumps(cluster)}])
            if "runtime_projection_boundary_json" in compact_query:
                return RecordingResult({"boundary_json": json.dumps(boundary)})
            return RecordingResult()

    tx = QueryTx()
    packet = Neo4jProjectionStore._query_philosophy_view_subgraph_tx(tx, "chronology", 50)
    nodes, edges, clusters = Neo4jProjectionStore._filter_query_surfaces(
        packet["nodes"],
        packet["edges"],
        packet["clusters"],
        layers={"historical-relation"},
        predicates={"has-dossier"},
        limit=50,
    )

    assert packet["view"]["view_id"] == "chronology"
    assert nodes[0]["node_id"] == "atlas-row:A01"
    assert edges[0]["predicate_id"] == "has-dossier"
    assert clusters[0]["cluster_id"] == "cluster:region:test"
    assert packet["runtime_projection_boundary"]["runtime_owner"] == "abyss-stack"
    assert any("TosPhilosophyViewProjection" in query for query in tx.queries)


def test_settings_treats_unreadable_stack_env_as_optional(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    stack_env_path = tmp_path / "stack.env"
    config_path.write_text("service:\n  name: tos-graph\n  port: 5410\n", encoding="utf-8")
    stack_env_path.write_text("NEO4J_AUTH=neo4j/not-used\n", encoding="utf-8")
    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == stack_env_path:
            raise PermissionError("stack env is mounted but unreadable")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setenv("TOS_GRAPH_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("TOS_GRAPH_STACK_ENV_PATH", str(stack_env_path))
    monkeypatch.delenv("NEO4J_AUTH", raising=False)
    monkeypatch.delenv("TOS_GRAPH_NEO4J_PASSWORD", raising=False)

    settings = load_settings()

    assert settings.service_name == "tos-graph"
    assert settings.neo4j_password is None
