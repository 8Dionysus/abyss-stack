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
    philosophy_graph_projection_path: str
    philosophy_graph_projection_exists: bool
    philosophy_post_planting_audit_path: str
    philosophy_post_planting_audit_exists: bool
    default_view: str
    default_philosophy_view: str


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


class PhilosophyStatusResponse(BaseModel):
    schema: str
    projection_exists: bool
    projection_path: str
    atlas_projection_path: str
    graph_views_path: str
    counts: dict[str, int]
    views: list[str]
    graph_layers: list[str]
    visibility_model: dict[str, Any] = {}
    snapshot_review: dict[str, Any] = {}
    runtime_projection_boundary: dict[str, Any]


class PhilosophyViewsResponse(BaseModel):
    schema: str
    views: list[dict[str, Any]]
    counts: dict[str, int]
    graph_layers: list[dict[str, Any]]
    layer_counts: list[dict[str, Any]] = []
    visibility_model: dict[str, Any] = {}
    runtime_projection_boundary: dict[str, Any]


class PhilosophyViewResponse(BaseModel):
    schema: str
    view: dict[str, Any]
    subgraph_contract: dict[str, Any] = {}
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    clusters: list[dict[str, Any]] = []
    review_packet: dict[str, Any] | None = None
    node_count: int
    edge_count: int
    source_refs: list[str]
    counts: dict[str, int]
    runtime_projection_boundary: dict[str, Any]


class PhilosophyLayersResponse(BaseModel):
    schema: str
    graph_layers: list[dict[str, Any]]
    layer_counts: list[dict[str, Any]]
    visibility_model: dict[str, Any]
    runtime_projection_boundary: dict[str, Any]


class PhilosophyContractsResponse(BaseModel):
    schema: str
    source_contract_refs: dict[str, str]
    runtime_contract: dict[str, Any]
    views: list[dict[str, Any]]
    node_kinds: list[str]
    edge_predicates: list[str]
    graph_layers: list[str]
    cluster_kinds: list[str]
    review_packet_fields: list[str]
    runtime_projection_boundary: dict[str, Any]


class PhilosophyClustersResponse(BaseModel):
    schema: str
    view_id: str | None
    cluster_kind: str | None
    clusters: list[dict[str, Any]]
    cluster_count: int
    counts: dict[str, int]
    source_refs: list[str]
    runtime_projection_boundary: dict[str, Any]


class PhilosophyReviewPacketResponse(BaseModel):
    schema: str
    packet: dict[str, Any]
    runtime_projection_boundary: dict[str, Any]
    authority_note: str


class PhilosophySnapshotResponse(BaseModel):
    schema: str
    snapshot_review: dict[str, Any]
    runtime_projection_boundary: dict[str, Any]
    authority_note: str


class PhilosophyAuditResponse(BaseModel):
    schema: str
    audit_exists: bool
    audit_path: str
    audit: dict[str, Any]
    authority_note: str


class PhilosophyUnresolvedResponse(BaseModel):
    schema: str
    view_id: str | None
    unresolved: list[dict[str, Any]]
    unresolved_count: int
    runtime_projection_boundary: dict[str, Any]


class PhilosophySearchResponse(BaseModel):
    schema: str
    query: str
    result_count: int
    results: list[dict[str, Any]]
    authority_note: str


class PhilosophyPacketResponse(BaseModel):
    schema: str
    query: str
    view_id: str | None
    result_count: int
    results: list[dict[str, Any]]
    view: dict[str, Any] | None
    counts: dict[str, int]
    runtime_projection_boundary: dict[str, Any]
    authority_note: str


class PhilosophyQueryViewResponse(BaseModel):
    schema: str
    query_backend: str
    fallback_reason: str | None = None
    view_id: str
    view: dict[str, Any]
    query_contract: dict[str, Any]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    clusters: list[dict[str, Any]] = []
    node_count: int
    edge_count: int
    cluster_count: int
    layers: list[str]
    predicates: list[str]
    limit: int
    source_refs: list[str]
    runtime_projection_boundary: dict[str, Any]
    authority_note: str


class PhilosophyQueryNeighborhoodResponse(BaseModel):
    schema: str
    query_backend: str
    fallback_reason: str | None = None
    node_id: str
    node: dict[str, Any]
    neighbors: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    depth: int
    layers: list[str]
    predicates: list[str]
    limit: int
    source_refs: list[str]
    runtime_projection_boundary: dict[str, Any]
    authority_note: str


class PhilosophyQueryPathResponse(BaseModel):
    schema: str
    query_backend: str
    fallback_reason: str | None = None
    from_id: str
    to_id: str
    found: bool
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    max_depth: int
    layers: list[str]
    predicates: list[str]
    source_refs: list[str]
    runtime_projection_boundary: dict[str, Any]
    authority_note: str


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
    constraint_count: int | None = None
    scale_export_row_counts: dict[str, int] = {}
