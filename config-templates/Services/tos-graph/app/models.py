from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: str
    route_default: str
    write_enabled: bool
    projection_mode: str
    neo4j_configured: bool
    neo4j_ready: bool
    neo4j_note: str
    tos_root: str
    tos_root_exists: bool


class RouteEntry(BaseModel):
    route: str
    label: str
    edge_count: int
    has_source_node: bool
    selected: bool


class RouteListResponse(BaseModel):
    routes: list[RouteEntry]


class RouteTreeResponse(BaseModel):
    route: str
    source_node: dict[str, Any] | None
    family_counts: dict[str, int]
    edge_count: int
    node_count: int


class RouteGraphResponse(BaseModel):
    route: str
    source_node: dict[str, Any] | None
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    diagnostics: dict[str, Any]


class ProjectSyncResponse(BaseModel):
    route: str
    status: str
    node_count: int
    edge_count: int
    projection_target: str
    note: str
    deleted_node_count: int | None = None
    deleted_edge_count: int | None = None
