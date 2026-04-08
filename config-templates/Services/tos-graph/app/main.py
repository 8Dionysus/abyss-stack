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
from .neo4j_store import Neo4jProjectionStore, describe_neo4j_store
from .projector import RouteProjector
from .tos_reader import ToSReader, ToSReaderError
from .ui import render_index


settings = load_settings()
reader = ToSReader(settings.tos_root, settings.route_default)
neo4j_status = describe_neo4j_store(settings)
neo4j_store = Neo4jProjectionStore(settings, neo4j_status)
projector = RouteProjector(reader, neo4j_status, neo4j_store)

app = FastAPI(title="tos-graph", version="0.1.0")


def _handle_reader_error(exc: ToSReaderError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return render_index(settings, neo4j_status)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service=settings.service_name,
        status="ok",
        route_default=settings.route_default,
        write_enabled=settings.write_enabled,
        projection_mode=settings.projection_mode,
        neo4j_configured=neo4j_status.configured,
        neo4j_ready=neo4j_status.ready,
        neo4j_note=neo4j_status.note,
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


@app.get("/api/nodes/{node_id:path}")
def node_detail(node_id: str) -> dict[str, Any]:
    try:
        return reader.get_node(node_id)
    except ToSReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.get("/api/edges/{edge_id:path}")
def edge_detail(edge_id: str) -> dict[str, Any]:
    try:
        return reader.get_edge(edge_id)
    except ToSReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.post("/api/project/sync", response_model=ProjectSyncResponse)
def project_sync(route: str | None = None) -> ProjectSyncResponse:
    try:
        return ProjectSyncResponse(**projector.sync_route(route))
    except ToSReaderError as exc:
        raise _handle_reader_error(exc) from exc
