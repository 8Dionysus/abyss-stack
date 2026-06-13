from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "config-templates" / "Services" / "rag-api"


def load_module():
    if str(SERVICE_ROOT) not in sys.path:
        sys.path.insert(0, str(SERVICE_ROOT))
    spec = importlib.util.spec_from_file_location(
        "rag_api_main_under_test",
        SERVICE_ROOT / "app" / "main.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_semantic_inventory_payload_is_bounded_and_redacted(tmp_path: Path) -> None:
    module = load_module()
    sources_path = tmp_path / "sources.json"
    graph_path = tmp_path / "agentic-graph.v1.json"
    sources_path.write_text(
        json.dumps({"schema": "abyss_stack_rag_sources_v1", "sources": [{"id": "docs", "root": "/sources/docs"}]}),
        encoding="utf-8",
    )
    graph_path.write_text(
        json.dumps({"schema": "abyss_stack_agentic_rag_graph_v1", "nodes": [{"id": "retrieve"}], "edges": []}),
        encoding="utf-8",
    )
    module.SOURCES_PATH = sources_path
    module.AGENTIC_GRAPH_PATH = graph_path
    module.NEO4J_URI = "bolt://neo4j_user:secret_password@neo4j.example:7687"

    module.safe_http_json = lambda method, url, payload=None, timeout=45: {"ok": True, "url": url, "data": {}}
    module.postgres_semantic_inventory = lambda: {
        "ok": True,
        "tcp_ready": True,
        "schema_inventory_present": True,
        "schemas": ["public"],
        "relations": [{"schema": "public", "name": "events", "type": "BASE TABLE"}],
        "redaction": {"raw_rows_stored": False, "credentials_included": False},
    }
    module.neo4j_semantic_inventory = lambda: {
        "ok": True,
        "uri": module.safe_url_without_userinfo(module.NEO4J_URI),
        "graph_inventory_present": True,
        "labels": ["TosCorpusProjection"],
        "relationship_types": ["PROJECTS_NODE"],
        "redaction": {"raw_graph_properties_stored": False, "credentials_included": False},
    }

    payload = module.semantic_inventory_payload()

    assert payload["ok"] is True
    assert payload["semantic_inventory"]["inventory_complete"] is True
    assert payload["semantic_inventory"]["stack_owned_postgres_schema_inventory_present"] is True
    assert payload["semantic_inventory"]["stack_owned_neo4j_graph_inventory_present"] is True
    assert payload["rag"]["source_ids"] == ["docs"]
    assert payload["redaction"]["raw_database_rows_stored"] is False
    assert payload["redaction"]["raw_graph_properties_stored"] is False
    assert payload["redaction"]["raw_source_documents_stored"] is False
    assert payload["neo4j"]["uri"] == "bolt://neo4j.example:7687"
    neo4j_refs = [ref for ref in payload["evidence_refs"] if ref.get("probe") == "neo4j_bolt_inventory"]
    assert neo4j_refs == [{"url": "bolt://neo4j.example:7687", "ok": True, "probe": "neo4j_bolt_inventory"}]
    payload_json = json.dumps(payload).lower()
    assert "secret_password" not in payload_json
    assert "neo4j_user" not in payload_json
