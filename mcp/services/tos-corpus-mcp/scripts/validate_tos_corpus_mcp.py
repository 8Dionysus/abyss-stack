#!/usr/bin/env python3
from __future__ import annotations

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


def discover_source_safe_state(fixture_root: Path) -> tuple[ToSCorpusMCPState, str]:
    live_state = ToSCorpusMCPState.discover()
    if live_state.index_exists():
        return live_state, "live"
    write_source_safe_fixture(fixture_root)
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

        server = build_server(tos_root=state.tos_root, index_path=state.index_path)
        if server is None:
            raise SystemExit("MCP server did not build")

        print(
            json.dumps(
                {
                    "ok": True,
                    "resources": status["counts"].get("resources"),
                    "nodes": status["counts"].get("nodes"),
                    "graph_views": len(status["graph_views"]),
                    "validation_source": validation_source,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
