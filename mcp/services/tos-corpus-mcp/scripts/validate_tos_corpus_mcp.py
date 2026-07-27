#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tos_corpus_mcp.core import ToSCorpusMCPState  # noqa: E402
from tos_corpus_mcp.server import build_server  # noqa: E402

def write_source_safe_fixture(root: Path) -> Path:
    index_path = root / "ToS" / "derived-exports" / "tos_corpus_index.min.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "tos_corpus_index_v1",
        "owner_repo": "Tree-of-Sophia",
        "surface_kind": "derived_corpus_index",
        "counts": {
            "branches": 1,
            "manifests": 1,
            "nodes": 1,
            "relation_packs": 1,
            "relation_edges": 1,
            "resources": 2,
        },
        "authority_order": [
            {
                "layer": "canon",
                "owner_branch": "ToS/canon",
                "meaning": "reviewed authored nodes",
            }
        ],
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
            }
        ],
        "branches": [
            {
                "id": "canon",
                "path": "ToS/canon",
                "owner_surface": "ToS/canon/AGENTS.md",
                "authority_layer": "canon",
                "role": "canon",
            }
        ],
        "manifests": [],
        "nodes": [
            {
                "node_id": "tos.concept.zarathustra",
                "node_type": "concept",
                "label": "Zarathustra",
                "owner_branch": "ToS/canon",
                "authority_layer": "canon",
                "source_path": "ToS/canon/concept/zarathustra/node.json",
                "source_sha256": "0" * 64,
                "route_hint": None,
            }
        ],
        "relation_packs": [
            {
                "pack_id": "canon/relations/zarathustra",
                "path": "ToS/canon/relations/zarathustra/edges.csv",
                "route_hint": "relations/zarathustra",
                "owner_branch": "ToS/canon",
                "authority_layer": "canon",
                "edge_count": 1,
                "columns": ["edge_id", "from_id", "predicate_id", "to_id"],
                "sha256": "1" * 64,
            }
        ],
        "relation_edges": [
            {
                "edge_id": "fixture-edge",
                "pack_id": "canon/relations/zarathustra",
                "from_id": "tos.concept.zarathustra",
                "predicate_id": "names",
                "to_id": "tos.concept.overcoming",
                "owner_branch": "ToS/canon",
                "authority_layer": "canon",
                "layer": "source_linked",
                "status": "fixture",
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
                "path": "ToS/canon/concept/zarathustra/node.json",
                "resource_kind": "node_payload",
                "owner_branch": "ToS/canon",
                "authority_layer": "canon",
                "sha256": "0" * 64,
                "size_bytes": 120,
            },
        ],
        "diagnostics": [],
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    return index_path


def write_philosophy_projection_fixture(root: Path) -> Path:
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
        "changed_subgraph": {"available": False, "reason": "validator fixture"},
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
    projection_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    return projection_path


def discover_source_safe_state(fixture_root: Path) -> tuple[ToSCorpusMCPState, str]:
    live_state = ToSCorpusMCPState.discover()
    if live_state.index_exists() and live_state.philosophy_projection_exists():
        return live_state, "live"
    write_source_safe_fixture(fixture_root)
    write_philosophy_projection_fixture(fixture_root)
    return ToSCorpusMCPState.discover(tos_root=fixture_root), "fixture"


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/tos_corpus_mcp/core.py",
        "src/tos_corpus_mcp/server.py",
        "scripts/tos_corpus_mcp_server.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    with tempfile.TemporaryDirectory(prefix="tos-corpus-mcp-fixture-") as fixture_dir:
        state, validation_source = discover_source_safe_state(Path(fixture_dir))
        status = state.status()
        if not status["index_exists"]:
            raise SystemExit(f"missing ToS corpus index: {status['index_path']}")
        if int(status["counts"].get("resources") or 0) == 0:
            raise SystemExit("ToS corpus index reports no resources")
        if int(status["counts"].get("nodes") or 0) == 0:
            raise SystemExit("ToS corpus index reports no nodes")
        if not status["graph_views"]:
            raise SystemExit("ToS corpus index reports no graph views")

        packet = state.packet(query="zarathustra", limit=8)
        if packet["result_count"] == 0:
            raise SystemExit("ToS corpus packet returned no Zarathustra results")

        view = state.graph_view("corpus-topology")
        if view["view"]["layout_hint"] != "elk-layered-or-graphviz-dot":
            raise SystemExit("corpus-topology view lost its layout hint")

        philosophy_status = state.philosophy_status()
        if not philosophy_status["projection_exists"]:
            raise SystemExit(f"missing ToS philosophy graph projection: {philosophy_status['projection_path']}")
        if int(philosophy_status["counts"].get("nodes") or 0) == 0:
            raise SystemExit("ToS philosophy graph projection reports no nodes")
        philosophy_packet = state.philosophy_packet(query="dossier", view_id="chronology", limit=8)
        if not philosophy_packet["view"]:
            raise SystemExit("ToS philosophy graph packet returned no chronology view")
        philosophy_layers = state.philosophy_layers()
        if int(philosophy_layers["layer_counts"][0].get("cluster_count") or 0) == 0:
            raise SystemExit("ToS philosophy graph layers returned no clusters")
        philosophy_contracts = state.philosophy_contracts()
        if not philosophy_contracts["views"]:
            raise SystemExit("ToS philosophy graph contracts returned no view contracts")
        philosophy_scale_manifest = state.philosophy_scale_manifest(view_id="chronology")
        if int(philosophy_scale_manifest["tables"]["nodes"].get("row_count") or 0) == 0:
            raise SystemExit("ToS philosophy scale manifest returned no nodes")
        philosophy_view = state.philosophy_view("chronology")
        first_edge = next((edge for edge in philosophy_view["edges"] if edge.get("from_id") and edge.get("to_id")), None)
        if first_edge is None:
            raise SystemExit("ToS philosophy chronology view returned no path-checkable edge")
        philosophy_path = state.philosophy_path_between(
            str(first_edge["from_id"]),
            str(first_edge["to_id"]),
            layers=[str(layer) for layer in first_edge.get("graph_layers", [])],
        )
        if not philosophy_path["found"]:
            raise SystemExit("ToS philosophy path packet did not find the sampled chronology edge route")
        philosophy_review = state.philosophy_review_packet("chronology")
        if not philosophy_review["packet"].get("cluster_summaries"):
            raise SystemExit("ToS philosophy graph review packet returned no cluster summaries")
        if philosophy_packet["result_count"] == 0:
            raise SystemExit("ToS philosophy graph packet returned no dossier results")

        server = build_server(tos_root=state.tos_root, index_path=state.index_path)
        if server is None:
            raise SystemExit("MCP server did not build")
        tools = asyncio.run(server.list_tools())
        if not tools:
            raise SystemExit("MCP server published no tools")
        unsafe_tools = [
            tool.name
            for tool in tools
            if tool.annotations is None
            or tool.annotations.readOnlyHint is not True
            or tool.annotations.destructiveHint is not False
            or tool.annotations.idempotentHint is not True
            or tool.annotations.openWorldHint is not False
        ]
        if unsafe_tools:
            raise SystemExit(
                "MCP tools lost the closed-world read-only contract: "
                + ", ".join(sorted(unsafe_tools))
            )

        print(
            json.dumps(
                {
                    "ok": True,
                    "resources": status["counts"].get("resources"),
                    "nodes": status["counts"].get("nodes"),
                    "graph_views": len(status["graph_views"]),
                    "philosophy_nodes": philosophy_status["counts"].get("nodes"),
                    "philosophy_views": len(philosophy_status["views"]),
                    "philosophy_clusters": philosophy_status["counts"].get("clusters"),
                    "philosophy_review_packets": philosophy_status["counts"].get("review_packets"),
                    "tool_count": len(tools),
                    "policy_family": "read",
                    "validation_source": validation_source,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
