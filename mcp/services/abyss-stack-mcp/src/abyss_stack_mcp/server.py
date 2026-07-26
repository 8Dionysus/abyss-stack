"""MCP transport surface for separate abyss-stack read and candidate planes."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from ._http_auth import http_auth_kwargs, transport_settings
from .core import ObservationStore, StackMCPApplication


LOGGER = logging.getLogger(__name__)
READ_PORT = 5431
CANDIDATE_PORT = 5433
PolicyMode = Literal["read", "candidate"]
CatalogLimit = Annotated[int, Field(ge=1, le=64)]
CatalogBudget = Annotated[int, Field(ge=512, le=131_072)]


def configured_policy_family() -> PolicyMode:
    value = os.environ.get("ABYSS_STACK_MCP_POLICY_FAMILY", "read").strip()
    if value not in {"read", "candidate"}:
        raise SystemExit("ABYSS_STACK_MCP_POLICY_FAMILY must be read or candidate")
    return value  # type: ignore[return-value]


def _contour(policy_family: PolicyMode) -> tuple[int, str, str, str]:
    upper = policy_family.upper()
    return (
        READ_PORT if policy_family == "read" else CANDIDATE_PORT,
        f"ABYSS_STACK_MCP_{upper}_BEARER_TOKEN",
        f"abyss-stack-mcp-{policy_family}-bearer-token",
        f"abyss-stack-mcp:{policy_family}",
    )


def _auth_kwargs(policy_family: PolicyMode) -> dict[str, Any]:
    port, env_name, credential_name, scope = _contour(policy_family)
    return http_auth_kwargs(
        port,
        token_env_var=env_name,
        credential_name=credential_name,
        auth_scope=scope,
        client_id=f"abyss-stack-mcp-{policy_family}-consumer",
    )


def _run_server(server: Any, policy_family: PolicyMode) -> None:
    port, _, _, _ = _contour(policy_family)
    settings = transport_settings(port)
    _auth_kwargs(policy_family)
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    assert settings.host is not None
    assert settings.port is not None
    server.settings.host = settings.host
    server.settings.port = settings.port
    server.run(transport="streamable-http")


def build_server(
    observation_path: str | Path | None = None,
    *,
    policy_family: PolicyMode | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'mcp'. Install with: python -m pip install -e ."
        ) from exc

    mode = policy_family or configured_policy_family()
    application = StackMCPApplication(
        ObservationStore(observation_path),
        policy_family=mode,
    )
    read_annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    candidate_annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    mcp = FastMCP(
        f"abyss-stack-mcp-{mode}",
        instructions=(
            "Inspect stack-owned source/package/deploy/process/endpoint/consumer "
            "evidence or prepare non-executing bounded runtime plans. This server "
            "does not proxy owner tools and never executes a plan."
        ),
        json_response=True,
        **_auth_kwargs(mode),
    )

    if mode == "read":

        @mcp.tool(annotations=read_annotations, structured_output=True)
        def stack_runtime_catalog(
            organ_id: str | None = None,
            policy_family: Literal[
                "read", "candidate", "internal_effect", "external_effect"
            ]
            | None = None,
            max_results: CatalogLimit = 32,
            byte_budget: CatalogBudget = 32_768,
        ) -> dict[str, Any]:
            """List compact runtime subjects without loading detailed schemas."""
            return application.catalog(
                organ_id=organ_id,
                policy_family=policy_family,
                max_results=max_results,
                byte_budget=byte_budget,
            )

        @mcp.tool(annotations=read_annotations, structured_output=True)
        def stack_runtime_inspect(
            organ_id: str,
            policy_family: Literal[
                "read", "candidate", "internal_effect", "external_effect"
            ],
            view: Literal[
                "identity",
                "parity",
                "process",
                "endpoint",
                "registry",
                "consumer",
                "schema",
                "freshness",
                "canary",
                "rollback",
                "drift",
                "full",
            ] = "identity",
        ) -> dict[str, Any]:
            """Inspect one exact runtime subject and one bounded evidence view."""
            return application.inspect(
                organ_id,
                policy_family,
                view=view,
            )
    else:

        @mcp.tool(annotations=candidate_annotations, structured_output=True)
        def stack_prepare_runtime_plan(
            organ_id: str,
            target_policy_family: Literal[
                "read", "candidate", "internal_effect", "external_effect"
            ],
            plan_kind: Literal["sync", "deploy", "activate", "restart", "rollback"],
            expected_observation_digest: str,
        ) -> dict[str, Any]:
            """Prepare a content-addressed candidate; never execute runtime effects."""
            return application.prepare_plan(
                organ_id,
                target_policy_family,
                plan_kind,
                expected_observation_digest=expected_observation_digest,
            )

    LOGGER.info("abyss-stack MCP %s plane ready", mode)
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mode = configured_policy_family()
    _run_server(build_server(policy_family=mode), mode)
