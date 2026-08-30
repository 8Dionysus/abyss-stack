from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote, unquote

from pydantic import Field

from ._http_auth import http_auth_config
from ._runtime_config import SERVICE_CONFIG
from .core import AoAKagMCPState
from .runtime import build_application


LOGGER = logging.getLogger(__name__)
Detail = Literal["compact", "summary", "full"]
Strategy = Literal["auto", "exact", "lexical", "semantic", "hybrid", "graph"]
Direction = Literal["outgoing", "incoming", "both"]
PageLimit = Annotated[int, Field(ge=1, le=10)]
TraversalDepth = Annotated[int, Field(ge=1, le=4)]


def _run_server(server: Any) -> None:
    from ._modern_runtime import run_server

    run_server(server, _read_http_auth_config())


def _read_http_auth_config() -> Any:
    contour = SERVICE_CONFIG.contour("read")
    return http_auth_config(contour.port, **contour.auth.as_kwargs())


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _uri(resource_class: str, identifier: str, owner: str | None = None) -> str:
    segments = [resource_class]
    if owner:
        segments.append(quote(owner, safe=""))
    segments.append(quote(identifier, safe=""))
    return "aoa-kag://" + "/".join(segments)


def build_server(
    workspace_root: str | Path | None = None,
    aoa_kag_root: str | Path | None = None,
    artifact_root: str | Path | None = None,
    provider_map_path: str | Path | None = None,
    readiness_path: str | Path | None = None,
    coverage_path: str | Path | None = None,
    stack_root: str | Path | None = None,
) -> Any:
    try:
        from ._modern_runtime import ModernMCPServer  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'mcp'. Install with: python -m pip install -e ."
        ) from exc

    state = AoAKagMCPState.discover(
        workspace_root=workspace_root,
        aoa_kag_root=aoa_kag_root,
        artifact_root=artifact_root,
        provider_map_path=provider_map_path,
        readiness_path=readiness_path,
        coverage_path=coverage_path,
    )
    application = build_application(state, stack_root=stack_root)
    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
    mcp = ModernMCPServer(
        SERVICE_CONFIG.server_name("read"),
        version=SERVICE_CONFIG.package_version,
        instructions=(
            "Discover KAG capabilities, search owner-qualified repository knowledge, "
            "read returned aoa-kag:// resources, traverse bounded relations, and inspect "
            "the evidence trace used for each answer."
        ),
        **_read_http_auth_config().server_kwargs,
    )

    @mcp.tool(annotations=annotations, structured_output=True)
    def kag_discover(
        owner: str | None = None,
        detail: Detail = "compact",
    ) -> dict[str, Any]:
        """Discover KAG owners, record classes, retrieval strategies, projections, and bounds."""
        return application.discover(owner=owner, detail=detail)

    @mcp.tool(annotations=annotations, structured_output=True)
    def kag_search(
        query: str,
        strategy: Strategy = "auto",
        owner: str | None = None,
        record_class: str | None = None,
        kind: str | None = None,
        document_role: str | None = None,
        surface_state: str | None = None,
        path: str | None = None,
        path_prefix: str | None = None,
        detail: Detail = "compact",
        limit: PageLimit = 10,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Search KAG through an explicit or automatically selected retrieval strategy."""
        return application.search(
            query,
            strategy=strategy,
            owner=owner,
            record_class=record_class,
            kind=kind,
            document_role=document_role,
            surface_state=surface_state,
            path=path,
            path_prefix=path_prefix,
            detail=detail,
            limit=limit,
            cursor=cursor,
        )

    @mcp.tool(annotations=annotations, structured_output=True)
    def kag_read(uri: str, detail: Detail = "full") -> dict[str, Any]:
        """Read one addressable KAG owner, record, source, schema, evidence, or projection resource."""
        return application.read(uri, detail=detail)

    @mcp.tool(annotations=annotations, structured_output=True)
    def kag_traverse(
        source_ids: list[str],
        owner: str | None = None,
        query: str = "",
        direction: Direction = "outgoing",
        relation_kinds: list[str] | None = None,
        max_depth: TraversalDepth = 2,
        detail: Detail = "compact",
        limit: PageLimit = 10,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Traverse owner-qualified KAG relations with bounded depth and complete path evidence."""
        return application.traverse(
            source_ids,
            owner=owner,
            query=query,
            direction=direction,
            relation_kinds=relation_kinds,
            max_depth=max_depth,
            detail=detail,
            limit=limit,
            cursor=cursor,
        )

    @mcp.tool(annotations=annotations, structured_output=True)
    def kag_explain(trace_id: str, detail: Detail = "summary") -> dict[str, Any]:
        """Explain the route, projections, degradation, and evidence behind one KAG trace."""
        return application.explain(trace_id, detail=detail)

    @mcp.resource(
        "aoa-kag://capabilities",
        description="Current KAG owners, retrieval strategies, bounds, and projection state.",
        mime_type="application/json",
    )
    def capabilities_resource() -> str:
        return _json(application.discover(detail="summary"))

    @mcp.resource(
        "aoa-kag://owners/{repo}/manifest",
        description="Canonical manifest and freshness state for one repository owner.",
        mime_type="application/json",
    )
    def owner_manifest_resource(repo: str) -> str:
        return _json(
            application.read(f"aoa-kag://owners/{quote(repo, safe='')}/manifest")
        )

    @mcp.resource(
        "aoa-kag://records/{qualified_id}",
        description="One owner-qualified KAG entity, event, artifact, assertion, anchor, or relation.",
        mime_type="application/json",
    )
    def record_resource(qualified_id: str) -> str:
        return _json(application.read(_uri("records", unquote(qualified_id))))

    @mcp.resource(
        "aoa-kag://documents/{document_id}",
        description="One addressable retrieval document with provenance and source links.",
        mime_type="application/json",
    )
    def document_resource(document_id: str) -> str:
        return _json(application.read(_uri("documents", unquote(document_id))))

    @mcp.resource(
        "aoa-kag://anchors/{anchor_id}",
        description="One source anchor resolving a KAG claim or record to repository content.",
        mime_type="application/json",
    )
    def anchor_resource(anchor_id: str) -> str:
        return _json(application.read(_uri("anchors", unquote(anchor_id))))

    @mcp.resource(
        "aoa-kag://sources/{repo}/{document_id}",
        description="Bounded source content for one repository-owned retrieval document.",
        mime_type="application/json",
    )
    def source_resource(repo: str, document_id: str) -> str:
        return _json(
            application.read(_uri("sources", unquote(document_id), unquote(repo)))
        )

    @mcp.resource(
        "aoa-kag://evidence/{trace_id}",
        description="Retrieval route, projection state, and evidence retained for one trace.",
        mime_type="application/json",
    )
    def evidence_resource(trace_id: str) -> str:
        return _json(application.read(_uri("evidence", unquote(trace_id))))

    @mcp.resource(
        "aoa-kag://schemas/{name}",
        description="One public aoa-kag JSON Schema used by KAG records or MCP results.",
        mime_type="application/json",
    )
    def schema_resource(name: str) -> str:
        return _json(application.read(_uri("schemas", unquote(name))))

    @mcp.resource(
        "aoa-kag://projections/{digest}",
        description="Runtime projection digest, target states, and materialization evidence.",
        mime_type="application/json",
    )
    def projection_resource(digest: str) -> str:
        return _json(application.read(_uri("projections", unquote(digest))))

    LOGGER.info("AoA KAG MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _run_server(build_server())
