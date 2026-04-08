from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .config import load_settings
from .models import (
    HealthResponse,
    ProjectSyncResponse,
    RouteGraphResponse,
    RouteListResponse,
    RouteTreeResponse,
)
from .neo4j_store import describe_neo4j_store
from .projector import PreviewProjector
from .tos_reader import ToSReader, ToSReaderError


settings = load_settings()
reader = ToSReader(settings.tos_root, settings.route_default)
neo4j_status = describe_neo4j_store(settings.neo4j_uri, settings.neo4j_user)
projector = PreviewProjector(reader, neo4j_status)

app = FastAPI(title="tos-graph", version="0.1.0")


def _handle_reader_error(exc: ToSReaderError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>tos-graph</title>
    <style>
      body {{ font-family: ui-monospace, SFMono-Regular, monospace; margin: 2rem; background: #f4efe6; color: #1b1b1b; }}
      .card {{ max-width: 880px; background: #fffdf8; border: 1px solid #d7ccb8; padding: 1.25rem; }}
      code {{ background: #efe6d8; padding: 0.1rem 0.25rem; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>tos-graph</h1>
      <p>Preview-first route helper for Tree of Sophia.</p>
      <p>Default route: <code>{settings.route_default}</code></p>
      <p>Projection mode: <code>{settings.projection_mode}</code></p>
      <p>Write enabled: <code>{str(settings.write_enabled).lower()}</code></p>
      <p>Primary APIs: <code>/health</code>, <code>/api/routes</code>, <code>/api/tree</code>, <code>/api/graph</code>.</p>
    </div>
  </body>
</html>
""".strip()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service=settings.service_name,
        status="ok",
        route_default=settings.route_default,
        write_enabled=settings.write_enabled,
        projection_mode=settings.projection_mode,
        tos_root=settings.tos_root.as_posix(),
        tos_root_exists=settings.tos_root.exists(),
    )


@app.get("/api/routes", response_model=RouteListResponse)
def list_routes() -> RouteListResponse:
    return RouteListResponse(routes=reader.list_routes())


@app.get("/api/tree", response_model=RouteTreeResponse)
def route_tree(route: str | None = None) -> RouteTreeResponse:
    try:
        return RouteTreeResponse(**reader.get_route_tree(route))
    except ToSReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.get("/api/graph", response_model=RouteGraphResponse)
def route_graph(route: str | None = None) -> RouteGraphResponse:
    try:
        return RouteGraphResponse(**reader.get_route_graph(route))
    except ToSReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.get("/api/nodes/{node_id}")
def node_detail(node_id: str) -> dict[str, Any]:
    try:
        return reader.get_node(node_id)
    except ToSReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.get("/api/edges/{edge_id}")
def edge_detail(edge_id: str) -> dict[str, Any]:
    try:
        return reader.get_edge(edge_id)
    except ToSReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.post("/api/project/sync", response_model=ProjectSyncResponse)
def project_sync(route: str | None = None) -> ProjectSyncResponse:
    try:
        return ProjectSyncResponse(**projector.sync_route_preview(route))
    except ToSReaderError as exc:
        raise _handle_reader_error(exc) from exc
