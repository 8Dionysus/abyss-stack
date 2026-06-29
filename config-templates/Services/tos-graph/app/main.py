from __future__ import annotations

import csv
import json
from pathlib import Path
from io import StringIO
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import load_settings
from .corpus_reader import ToSCorpusReader, ToSCorpusReaderError
from .models import (
    CorpusGraphViewResponse,
    CorpusSearchResponse,
    CorpusStatusResponse,
    CorpusSummaryResponse,
    HealthResponse,
    PhilosophyClustersResponse,
    PhilosophyLayersResponse,
    PhilosophyAuditResponse,
    PhilosophyPacketResponse,
    PhilosophyReviewPacketResponse,
    PhilosophySearchResponse,
    PhilosophySnapshotResponse,
    PhilosophyStatusResponse,
    PhilosophyUnresolvedResponse,
    PhilosophyViewResponse,
    PhilosophyViewsResponse,
    ProjectSyncResponse,
)
from .neo4j_store import Neo4jProjectionStore, describe_neo4j_store
from .philosophy_reader import SCALE_EXPORT_COLUMNS, ToSPhilosophyProjectionReader, ToSPhilosophyReaderError
from .projector import CorpusProjector, PhilosophyProjector
from .ui import render_index


settings = load_settings()
reader = ToSCorpusReader(settings)
philosophy_reader = ToSPhilosophyProjectionReader(settings)
neo4j_status = describe_neo4j_store(settings)
neo4j_store = Neo4jProjectionStore(settings, neo4j_status)
projector = CorpusProjector(reader, neo4j_status, neo4j_store)
philosophy_projector = PhilosophyProjector(philosophy_reader, neo4j_status, neo4j_store)


def _static_root() -> Path:
    app_static = Path(__file__).resolve().parent / "static"
    if app_static.exists():
        return app_static
    return Path(__file__).resolve().parents[1] / "frontend" / "dist"


app = FastAPI(title="tos-graph", version="0.2.0")
app.mount(
    "/static",
    StaticFiles(directory=_static_root(), check_dir=False),
    name="static",
)


def _handle_reader_error(exc: ToSCorpusReaderError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _handle_philosophy_reader_error(exc: ToSPhilosophyReaderError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _layer_set(raw_layers: str | None) -> set[str]:
    if not raw_layers:
        return set()
    return {layer.strip() for layer in raw_layers.split(",") if layer.strip()}


def _csv_stream(table_name: str, rows: list[dict[str, Any]]) -> Iterator[str]:
    fieldnames = SCALE_EXPORT_COLUMNS[table_name]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    for row in rows:
        writer.writerow(row)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def _jsonl_stream(rows: list[dict[str, Any]]) -> Iterator[str]:
    for row in rows:
        yield json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return render_index(settings, neo4j_status)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service=settings.service_name,
        status="ok",
        write_enabled=settings.write_enabled,
        projection_mode=settings.projection_mode,
        neo4j_configured=neo4j_status.configured,
        neo4j_ready=neo4j_status.ready,
        neo4j_note=neo4j_status.note,
        tos_root=settings.tos_root.as_posix(),
        tos_root_exists=settings.tos_root.exists(),
        corpus_index_path=settings.corpus_index_path.as_posix(),
        corpus_index_exists=settings.corpus_index_path.exists(),
        philosophy_graph_projection_path=settings.philosophy_graph_projection_path.as_posix(),
        philosophy_graph_projection_exists=settings.philosophy_graph_projection_path.exists(),
        philosophy_post_planting_audit_path=settings.philosophy_post_planting_audit_path.as_posix(),
        philosophy_post_planting_audit_exists=settings.philosophy_post_planting_audit_path.exists(),
        default_view=settings.default_view,
        default_philosophy_view=settings.default_philosophy_view,
    )


@app.get("/api/corpus/status", response_model=CorpusStatusResponse)
def corpus_status() -> CorpusStatusResponse:
    return CorpusStatusResponse(**reader.status())


@app.get("/api/corpus/summary", response_model=CorpusSummaryResponse)
def corpus_summary() -> CorpusSummaryResponse:
    try:
        return CorpusSummaryResponse(**reader.summary())
    except ToSCorpusReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.get("/api/corpus/search", response_model=CorpusSearchResponse)
def corpus_search(query: str = "", limit: int = 20) -> CorpusSearchResponse:
    try:
        return CorpusSearchResponse(**reader.search(query=query, limit=limit))
    except ToSCorpusReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.get("/api/corpus/graph-views/{view_id}", response_model=CorpusGraphViewResponse)
def corpus_graph_view(view_id: str, limit: int = 100) -> CorpusGraphViewResponse:
    try:
        return CorpusGraphViewResponse(**reader.graph_view(view_id=view_id, limit=limit))
    except ToSCorpusReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.get("/api/corpus/nodes/{node_id:path}")
def node_detail(node_id: str) -> dict[str, Any]:
    try:
        return reader.node(node_id)
    except ToSCorpusReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.get("/api/corpus/relation-packs/{pack_id:path}")
def relation_pack_detail(pack_id: str) -> dict[str, Any]:
    try:
        return reader.relation_pack(pack_id)
    except ToSCorpusReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.get("/api/philosophy/status", response_model=PhilosophyStatusResponse)
def philosophy_status() -> PhilosophyStatusResponse:
    return PhilosophyStatusResponse(**philosophy_reader.status())


@app.get("/api/philosophy/views", response_model=PhilosophyViewsResponse)
def philosophy_views() -> PhilosophyViewsResponse:
    try:
        return PhilosophyViewsResponse(**philosophy_reader.views())
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/layers", response_model=PhilosophyLayersResponse)
def philosophy_layers() -> PhilosophyLayersResponse:
    try:
        return PhilosophyLayersResponse(**philosophy_reader.layers())
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/views/{view_id}", response_model=PhilosophyViewResponse)
def philosophy_view(view_id: str) -> PhilosophyViewResponse:
    try:
        return PhilosophyViewResponse(**philosophy_reader.view(view_id))
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/views/{view_id}/clusters", response_model=PhilosophyClustersResponse)
def philosophy_view_clusters(view_id: str, kind: str | None = None, limit: int = 80) -> PhilosophyClustersResponse:
    try:
        return PhilosophyClustersResponse(**philosophy_reader.clusters(view_id=view_id, cluster_kind=kind, limit=limit))
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/clusters", response_model=PhilosophyClustersResponse)
def philosophy_clusters(
    view_id: str | None = None,
    kind: str | None = None,
    limit: int = 80,
) -> PhilosophyClustersResponse:
    try:
        return PhilosophyClustersResponse(**philosophy_reader.clusters(view_id=view_id, cluster_kind=kind, limit=limit))
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/review-packet", response_model=PhilosophyReviewPacketResponse)
def philosophy_review_packet(view_id: str = "chronology") -> PhilosophyReviewPacketResponse:
    try:
        return PhilosophyReviewPacketResponse(**philosophy_reader.review_packet(view_id))
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/snapshot", response_model=PhilosophySnapshotResponse)
def philosophy_snapshot() -> PhilosophySnapshotResponse:
    try:
        return PhilosophySnapshotResponse(**philosophy_reader.snapshot())
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/audit", response_model=PhilosophyAuditResponse)
def philosophy_audit() -> PhilosophyAuditResponse:
    try:
        return PhilosophyAuditResponse(**philosophy_reader.audit())
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/unresolved", response_model=PhilosophyUnresolvedResponse)
def philosophy_unresolved(view_id: str | None = None) -> PhilosophyUnresolvedResponse:
    try:
        return PhilosophyUnresolvedResponse(**philosophy_reader.unresolved(view_id=view_id))
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/search", response_model=PhilosophySearchResponse)
def philosophy_search(query: str = "", limit: int = 40) -> PhilosophySearchResponse:
    try:
        return PhilosophySearchResponse(**philosophy_reader.search(query=query, limit=limit))
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/packet", response_model=PhilosophyPacketResponse)
def philosophy_packet(query: str = "", view_id: str | None = None, limit: int = 20) -> PhilosophyPacketResponse:
    try:
        return PhilosophyPacketResponse(**philosophy_reader.packet(query=query, view_id=view_id, limit=limit))
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/nodes/{node_id:path}")
def philosophy_node(node_id: str) -> dict[str, Any]:
    try:
        return philosophy_reader.node(node_id)
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/edges/{edge_id:path}")
def philosophy_edge(edge_id: str) -> dict[str, Any]:
    try:
        return philosophy_reader.edge(edge_id)
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/neighborhood/{node_id:path}")
def philosophy_neighborhood(node_id: str, depth: int = 1, layers: str | None = None, limit: int = 120) -> dict[str, Any]:
    try:
        return philosophy_reader.neighborhood(node_id, depth=depth, layers=_layer_set(layers), limit=limit)
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/paths")
def philosophy_paths(
    from_id: str = Query(alias="from"),
    to_id: str = Query(alias="to"),
    layers: str | None = None,
    max_depth: int = 6,
) -> dict[str, Any]:
    try:
        return philosophy_reader.path_between(from_id, to_id, layers=_layer_set(layers), max_depth=max_depth)
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/scale-export/manifest")
def philosophy_scale_export_manifest(view_id: str | None = None, layers: str | None = None) -> dict[str, Any]:
    try:
        return philosophy_reader.scale_export_manifest(view_id=view_id, layers=_layer_set(layers))
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc


@app.get("/api/philosophy/scale-export/{table_name}.{file_format}")
def philosophy_scale_export_table(
    table_name: str,
    file_format: str,
    view_id: str | None = None,
    layers: str | None = None,
) -> StreamingResponse:
    if file_format not in {"csv", "jsonl"}:
        raise HTTPException(status_code=400, detail="file_format must be csv or jsonl")
    try:
        rows = philosophy_reader.scale_export_table(table_name, view_id=view_id, layers=_layer_set(layers))
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc
    filename = f"tos-philosophy-{table_name}.{file_format}"
    if file_format == "csv":
        return StreamingResponse(
            _csv_stream(table_name, rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return StreamingResponse(
        _jsonl_stream(rows),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/project/sync", response_model=ProjectSyncResponse)
def project_sync() -> ProjectSyncResponse:
    try:
        return ProjectSyncResponse(**projector.sync_corpus())
    except ToSCorpusReaderError as exc:
        raise _handle_reader_error(exc) from exc


@app.post("/api/philosophy/project/sync", response_model=ProjectSyncResponse)
def philosophy_project_sync() -> ProjectSyncResponse:
    try:
        return ProjectSyncResponse(**philosophy_projector.sync_philosophy())
    except ToSPhilosophyReaderError as exc:
        raise _handle_philosophy_reader_error(exc) from exc
