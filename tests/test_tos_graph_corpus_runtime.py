from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "config-templates" / "Services" / "tos-graph"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import TosGraphSettings  # noqa: E402
from app.corpus_reader import ToSCorpusReader  # noqa: E402
from app.neo4j_store import Neo4jProjectionStore, Neo4jStoreStatus  # noqa: E402
from app.projector import CorpusProjector  # noqa: E402


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


def settings_for(root: Path) -> TosGraphSettings:
    return TosGraphSettings(
        service_name="tos-graph",
        port=5410,
        config_path=root / "config.yaml",
        stack_env_path=root / "stack.env",
        tos_root=root,
        log_root=root / "logs",
        corpus_index_path=root / "ToS" / "derived-exports" / "tos_corpus_index.min.json",
        default_view="corpus-topology",
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
