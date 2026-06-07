from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: str
    write_enabled: bool
    projection_mode: str
    neo4j_configured: bool
    neo4j_ready: bool
    neo4j_note: str
    tos_root: str
    tos_root_exists: bool
    corpus_index_path: str
    corpus_index_exists: bool
    default_view: str


class CorpusStatusResponse(BaseModel):
    schema: str
    index_exists: bool
    index_path: str
    counts: dict[str, int]
    graph_views: list[str]
    authority_order: list[dict[str, Any]]
    runtime_projection_boundary: dict[str, Any]


class CorpusSummaryResponse(BaseModel):
    schema: str
    status: dict[str, Any]
    counts: dict[str, int]
    branches: list[dict[str, Any]]
    graph_views: list[dict[str, Any]]
    authority_order: list[dict[str, Any]]
    runtime_projection_boundary: dict[str, Any]


class CorpusSearchResponse(BaseModel):
    schema: str
    query: str
    result_count: int
    results: list[dict[str, Any]]
    authority_note: str


class CorpusGraphViewResponse(BaseModel):
    schema: str
    view: dict[str, Any]
    item_count: int
    items: list[dict[str, Any]]
    counts: dict[str, int]
    runtime_projection_boundary: dict[str, Any]


class ProjectSyncResponse(BaseModel):
    surface: str
    status: str
    node_count: int
    edge_count: int
    resource_count: int
    branch_count: int
    projection_target: str
    note: str
    deleted_node_count: int | None = None
    deleted_edge_count: int | None = None
