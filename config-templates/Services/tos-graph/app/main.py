from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .config import load_settings
from .corpus_reader import ToSCorpusReader, ToSCorpusReaderError
from .models import (
    CorpusGraphViewResponse,
    CorpusSearchResponse,
    CorpusStatusResponse,
    CorpusSummaryResponse,
    HealthResponse,
    ProjectSyncResponse,
)
from .neo4j_store import Neo4jProjectionStore, describe_neo4j_store
from .projector import CorpusProjector
from .ui import render_index


settings = load_settings()
reader = ToSCorpusReader(settings)
neo4j_status = describe_neo4j_store(settings)
neo4j_store = Neo4jProjectionStore(settings, neo4j_status)
projector = CorpusProjector(reader, neo4j_status, neo4j_store)

app = FastAPI(title="tos-graph", version="0.2.0")


def _handle_reader_error(exc: ToSCorpusReaderError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


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
        default_view=settings.default_view,
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


@app.post("/api/project/sync", response_model=ProjectSyncResponse)
def project_sync() -> ProjectSyncResponse:
    try:
        return ProjectSyncResponse(**projector.sync_corpus())
    except ToSCorpusReaderError as exc:
        raise _handle_reader_error(exc) from exc
