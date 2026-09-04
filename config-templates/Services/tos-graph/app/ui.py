from __future__ import annotations

import json
from pathlib import Path

from .config import TosGraphSettings
from .neo4j_store import Neo4jStoreStatus


INDEX_TEMPLATE = """<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Древо Софии</title>
    <link rel="stylesheet" href="/static/assets/tos-graph.css?v=__ASSET_VERSION__">
  </head>
  <body>
    <div id="app"></div>
    <script>
      window.__TOS_GRAPH_BOOT__ = __BOOT_PAYLOAD__;
    </script>
    <script type="module" src="/static/assets/tos-graph.js?v=__ASSET_VERSION__"></script>
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
    service_root = Path(__file__).resolve().parents[1]
    asset_roots = (Path(__file__).resolve().parent / "static", service_root / "frontend" / "dist")
    asset_mtimes = [
        asset.stat().st_mtime_ns
        for root in asset_roots
        for asset in (root / "assets" / "tos-graph.css", root / "assets" / "tos-graph.js")
        if asset.is_file()
    ]
    asset_version = str(max(asset_mtimes, default=0))
    return (
        INDEX_TEMPLATE
        .replace("__BOOT_PAYLOAD__", json.dumps(boot_payload, ensure_ascii=False))
        .replace("__ASSET_VERSION__", asset_version)
    )
