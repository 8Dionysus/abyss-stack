from __future__ import annotations

import json

from .config import TosGraphSettings
from .neo4j_store import Neo4jStoreStatus


INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Tree of Sophia Graph</title>
    <link rel="stylesheet" href="/static/assets/tos-graph.css">
  </head>
  <body>
    <div id="app"></div>
    <script>
      window.__TOS_GRAPH_BOOT__ = __BOOT_PAYLOAD__;
    </script>
    <script type="module" src="/static/assets/tos-graph.js"></script>
  </body>
</html>
"""


def render_index(settings: TosGraphSettings, neo4j_status: Neo4jStoreStatus) -> str:
    boot_payload = {
        "service": settings.service_name,
        "corpus_index_path": settings.corpus_index_path.as_posix(),
        "philosophy_graph_projection_path": settings.philosophy_graph_projection_path.as_posix(),
        "default_view": settings.default_view,
        "default_philosophy_view": settings.default_philosophy_view,
        "write_enabled": settings.write_enabled,
        "projection_mode": settings.projection_mode,
        "neo4j": {
            "configured": neo4j_status.configured,
            "ready": neo4j_status.ready,
            "database": neo4j_status.database,
            "note": neo4j_status.note,
        },
    }
    return INDEX_TEMPLATE.replace("__BOOT_PAYLOAD__", json.dumps(boot_payload, ensure_ascii=False))
