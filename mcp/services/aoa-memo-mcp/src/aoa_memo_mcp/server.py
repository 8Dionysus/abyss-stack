from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings
from .core import AoAMemoMCPState
from .organ_access import CANDIDATE_CAPABILITY_ID
from .organ_access import CANDIDATE_TOOL_BINDINGS
from .organ_access import READ_CAPABILITY_ID
from .organ_access import READ_RESOURCE_TEMPLATE_BINDINGS
from .organ_access import READ_TOOL_BINDINGS
from .organ_access import load_owner_manifest
from .organ_access import validate_runtime_bindings

LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "aoa-memo-mcp"
APPLICATION_VERSION = "0.2.0"
READ_HTTP_PORT = 5421
CANDIDATE_HTTP_PORT = 5434
DEFAULT_HTTP_PORT = READ_HTTP_PORT
PolicyFamily = Literal["read", "candidate"]

READ_TOKEN_ENV_VAR = "AOA_MEMO_MCP_READ_BEARER_TOKEN"
READ_CREDENTIAL_NAME = "aoa-memo-mcp-read-bearer-token"
READ_AUTH_SCOPE = "mcp:aoa-memo:read"
READ_CLIENT_ID = "aoa-loopback-codex:aoa-memo:read"

CANDIDATE_TOKEN_ENV_VAR = "AOA_MEMO_MCP_CANDIDATE_BEARER_TOKEN"
CANDIDATE_CREDENTIAL_NAME = "aoa-memo-mcp-candidate-bearer-token"
CANDIDATE_AUTH_SCOPE = "mcp:aoa-memo:candidate"
CANDIDATE_CLIENT_ID = "aoa-loopback-codex:aoa-memo:candidate"
CAPABILITY_PROFILE_ENV_VAR = "AOA_MEMO_MCP_CAPABILITY_PROFILE"


def _application_version() -> str:
    return APPLICATION_VERSION


def _bind_server_info_version(mcp: Any) -> None:
    low_level_server = getattr(mcp, "_mcp_server", None)
    if low_level_server is None or not hasattr(low_level_server, "version"):
        raise RuntimeError(
            "the pinned MCP SDK no longer exposes the server identity seam"
        )
    low_level_server.version = _application_version()


def configured_policy_family() -> PolicyFamily:
    value = os.environ.get("AOA_MCP_POLICY_FAMILY", "read").strip()
    if value not in {"read", "candidate"}:
        raise SystemExit("AOA_MCP_POLICY_FAMILY must be read or candidate")
    return value  # type: ignore[return-value]


def _contour(
    policy_family: PolicyFamily,
) -> tuple[int, str, str, str, str]:
    if policy_family == "read":
        return (
            READ_HTTP_PORT,
            READ_TOKEN_ENV_VAR,
            READ_CREDENTIAL_NAME,
            READ_AUTH_SCOPE,
            READ_CLIENT_ID,
        )
    return (
        CANDIDATE_HTTP_PORT,
        CANDIDATE_TOKEN_ENV_VAR,
        CANDIDATE_CREDENTIAL_NAME,
        CANDIDATE_AUTH_SCOPE,
        CANDIDATE_CLIENT_ID,
    )


def _contour_http_auth_kwargs(
    policy_family: PolicyFamily,
) -> dict[str, Any]:
    port, token_env_var, credential_name, auth_scope, client_id = _contour(
        policy_family
    )
    return _http_auth_kwargs(
        port,
        token_env_var=token_env_var,
        credential_name=credential_name,
        auth_scope=auth_scope,
        client_id=client_id,
    )


def _read_http_auth_kwargs() -> dict[str, Any]:
    return _contour_http_auth_kwargs("read")


def _expected_capability(policy_family: PolicyFamily) -> str:
    return (
        READ_CAPABILITY_ID
        if policy_family == "read"
        else CANDIDATE_CAPABILITY_ID
    )


def _apply_capability_profile(
    mcp: Any,
    *,
    policy_family: PolicyFamily,
    workspace_root: str | Path | None,
) -> None:
    profile = os.environ.get(CAPABILITY_PROFILE_ENV_VAR, "").strip()
    if not profile:
        return
    expected = _expected_capability(policy_family)
    if profile != expected:
        raise SystemExit(
            f"{CAPABILITY_PROFILE_ENV_VAR} must be {expected!r} for the "
            f"{policy_family} contour"
        )
    tool_names = set(
        READ_TOOL_BINDINGS.values()
        if policy_family == "read"
        else CANDIDATE_TOOL_BINDINGS.values()
    )
    template_names = set(
        READ_RESOURCE_TEMPLATE_BINDINGS.values()
        if policy_family == "read"
        else []
    )
    mcp._tool_manager._tools = {
        name: item
        for name, item in mcp._tool_manager._tools.items()
        if name in tool_names
    }
    mcp._resource_manager._resources = {}
    mcp._resource_manager._templates = {
        name: item
        for name, item in mcp._resource_manager._templates.items()
        if str(item.uri_template) in template_names
    }
    mcp._prompt_manager._prompts = {}
    validate_runtime_bindings(
        load_owner_manifest(workspace_root),
        capability_id=profile,
        tool_names=set(mcp._tool_manager._tools),
        resource_templates={
            str(item.uri_template)
            for item in mcp._resource_manager._templates.values()
        },
    )


def _default_http_capability_profile(policy_family: PolicyFamily) -> str | None:
    explicit = os.environ.get(CAPABILITY_PROFILE_ENV_VAR, "").strip()
    if explicit:
        return explicit
    port, *_ = _contour(policy_family)
    if _transport_settings(port).transport == "streamable-http":
        return _expected_capability(policy_family)
    return None


def _run_server(server: Any) -> None:
    policy_family = configured_policy_family()
    port, *_ = _contour(policy_family)
    settings = _transport_settings(port)
    _contour_http_auth_kwargs(policy_family)
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    assert settings.host is not None
    assert settings.port is not None
    server.configure_http(settings.host, settings.port)
    server.run(transport="streamable-http")


def build_server(
    workspace_root: str | Path | None = None,
    *,
    policy_family: PolicyFamily | None = None,
) -> Any:
    try:
        from ._modern_runtime import AbyssMCPServer  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'mcp'. Install with: python -m pip install -e ."
        ) from exc

    contour = policy_family or configured_policy_family()
    mcp = AbyssMCPServer(
        f"aoa-memo-mcp-{contour}",
        json_response=True,
        **_contour_http_auth_kwargs(contour),
    )
    _bind_server_info_version(mcp)
    read_only_tool = mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    candidate_tool = mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )

    def current_state() -> AoAMemoMCPState:
        return AoAMemoMCPState.discover(workspace_root)

    if contour == "read":

        @read_only_tool
        def aoa_memo_recall_brief(
            repo: str,
            intent: str = "",
        ) -> dict[str, Any]:
            """Return only reviewed durable-memory rows for one owner route."""
            return current_state().build_reviewed_brief(repo=repo, intent=intent)

        @read_only_tool
        def aoa_memo_recall_reviewed(
            query: str,
            mode: str = "brief",
            limit: int = 8,
        ) -> dict[str, Any]:
            """Search only reviewed durable-corpus memory read models."""
            return current_state().search(
                query=query,
                scope="reviewed",
                mode=mode,
                limit=max(1, min(int(limit), 12)),
            )

        @read_only_tool
        def aoa_memo_read_object(object_id: str) -> dict[str, Any]:
            """Read one object only when it belongs to the reviewed durable corpus."""
            return current_state().build_reviewed_memory_object(object_id)

        @read_only_tool
        def aoa_memo_brief(
            repo: str,
            intent: str = "",
        ) -> dict[str, Any]:
            """Return a compact memory route brief for a repository or host layer."""
            return current_state().build_brief(repo=repo, intent=intent)

        @read_only_tool
        def aoa_memo_search(
            query: str,
            scope: str = "all",
            mode: str = "brief",
        ) -> dict[str, Any]:
            """Search central memory contracts, local memo ports, and session indexes."""
            return current_state().search(query=query, scope=scope, mode=mode)

        @read_only_tool
        def aoa_memo_owner_orientation(
            plan: dict[str, Any],
            memo_bundle: dict[str, Any],
            observed_at: str | None = None,
            target_ref: str = "codex:current-request",
            attempt_no: int = 1,
        ) -> dict[str, Any]:
            """Deliver one pre-admitted owner-orientation bundle without writes."""
            return current_state().deliver_owner_orientation(
                plan=plan,
                memo_bundle=memo_bundle,
                observed_at=observed_at,
                target_ref=target_ref,
                attempt_no=attempt_no,
            )

        @read_only_tool
        def aoa_memo_validate_candidate(path: str) -> dict[str, Any]:
            """Validate a local memory candidate before reviewed intake."""
            return current_state().validate_candidate(path)

        @read_only_tool
        def aoa_memo_build_port_index(
            repo: str,
            check: bool = False,
        ) -> dict[str, Any]:
            """Build an in-memory local memo index or check its stored projection."""
            return current_state().build_port_index(
                repo=repo,
                write=False,
                check=check,
            )

        @read_only_tool
        def aoa_memo_validate_port(repo: str) -> dict[str, Any]:
            """Validate a local memo port contract, packets, and generated index."""
            return current_state().validate_port(repo)

        @read_only_tool
        def aoa_memo_pending_exports(repo: str) -> dict[str, Any]:
            """List local reviewed-intake exports and their landing readiness."""
            return current_state().list_pending_exports(repo)

        @read_only_tool
        def aoa_memo_landing_plan(
            repo: str,
            export_ref: str,
            object_kind: str = "decision",
            slug: str | None = None,
            title: str | None = None,
            summary: str | None = None,
            reviewed_at: str | None = None,
            run_dry_run: bool = False,
        ) -> dict[str, Any]:
            """Prepare or dry-run an aoa-memo landing plan without durable write."""
            return current_state().build_landing_plan(
                repo=repo,
                export_ref=export_ref,
                object_kind=object_kind,
                slug=slug,
                title=title,
                summary=summary,
                reviewed_at=reviewed_at,
                run_dry_run=run_dry_run,
            )

        @mcp.resource("aoa-memo://brief/repo/{repo}")
        def brief_resource(repo: str) -> str:
            return json.dumps(
                current_state().build_brief(repo),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-memo://memory/object/{object_id}")
        def memory_object_resource(object_id: str) -> str:
            return json.dumps(
                current_state().build_reviewed_memory_object(object_id),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-memo://session/{session_id}/rehydrate")
        def session_rehydrate_resource(session_id: str) -> str:
            return json.dumps(
                current_state().build_session_rehydrate(session_id),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-memo://repo/{repo}/local-port-status")
        def local_port_status_resource(repo: str) -> str:
            return json.dumps(
                current_state().build_local_port_status(repo),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-memo://repo/{repo}/memo-port-index")
        def memo_port_index_resource(repo: str) -> str:
            return json.dumps(
                current_state().build_port_index(repo),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-memo://repo/{repo}/memo-open-items")
        def memo_open_items_resource(repo: str) -> str:
            return json.dumps(
                current_state().read_resource(
                    f"aoa-memo://repo/{repo}/memo-open-items"
                ),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-memo://repo/{repo}/pending-exports")
        def pending_exports_resource(repo: str) -> str:
            return json.dumps(
                current_state().list_pending_exports(repo),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-memo://repo/{repo}/memo-vocabulary")
        def memo_vocabulary_resource(repo: str) -> str:
            del repo
            return json.dumps(
                current_state().build_memo_port_vocabulary(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-memo://intake/{packet_id}/review")
        def intake_review_resource(packet_id: str) -> str:
            return json.dumps(
                current_state().find_intake_review(packet_id),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.prompt(name="memo-brief")
        def memo_brief(repo: str, intent: str = "") -> str:
            """Prompt route for obtaining a memory brief."""
            return (
                f"Use aoa_memo_brief(repo={repo!r}, intent={intent!r}). "
                "Read the local port status, operation mode, owner note, and "
                "validation commands before acting."
            )

        @mcp.prompt(name="memo-landing-plan")
        def memo_landing_plan(repo: str, export_ref: str) -> str:
            """Prompt route for planning reviewed aoa-memo landing."""
            return (
                f"Use aoa_memo_pending_exports(repo={repo!r}), then "
                f"aoa_memo_landing_plan(repo={repo!r}, "
                f"export_ref={export_ref!r}, run_dry_run=True). "
                "Inspect readiness and dry-run output; durable landing still "
                "requires an aoa-memo source patch and validators."
            )

        @mcp.prompt(name="session-rehydrate")
        def session_rehydrate(session_id: str) -> str:
            """Prompt route for session evidence rehydration."""
            return (
                f"Use aoa-memo://session/{session_id}/rehydrate to get archive "
                "pointers. Inspect AGENTS.md, SESSION.md, manifest, and index "
                "before opening raw evidence."
            )

    else:

        @candidate_tool
        def aoa_memo_create_candidate(
            repo: str,
            evidence_refs: list[str],
            claim: str,
            source_trust: str = "review_required",
            kind: str = "route",
            family: str = "memory-access",
            scope: str = "repo",
            source_refs: list[str] | None = None,
        ) -> dict[str, Any]:
            """Create one repo-local memory candidate below durable memory authority."""
            return current_state().create_candidate(
                repo=repo,
                evidence_refs=evidence_refs,
                claim=claim,
                source_trust=source_trust,
                kind=kind,
                family=family,
                scope=scope,
                source_refs=source_refs,
            )

        @candidate_tool
        def aoa_memo_write_port_index(
            repo: str,
        ) -> dict[str, Any]:
            """Build and explicitly write the generated local memo index."""
            return current_state().build_port_index(
                repo=repo,
                write=True,
            )

        @candidate_tool
        def aoa_memo_prepare_intake_packet(
            repo: str,
            candidate_refs: list[str],
            receipt_refs: list[str] | None = None,
        ) -> dict[str, Any]:
            """Write a candidate-only reviewed-intake export packet."""
            return current_state().prepare_intake_packet(
                repo=repo,
                candidate_refs=candidate_refs,
                receipt_refs=receipt_refs,
            )

        @candidate_tool
        def aoa_memo_review_intake(path: str) -> dict[str, Any]:
            """Write a forwarding-check receipt without accepting durable memory."""
            return current_state().review_intake(path)

        @candidate_tool
        def aoa_memo_prepare_forwarding_receipt(path: str) -> dict[str, Any]:
            """Write a forwarding-check receipt without accepting durable memory."""
            return current_state().review_intake(path)

        @mcp.prompt(name="memo-intake")
        def memo_intake(repo: str, claim: str) -> str:
            """Prompt route for creating a repo-local memory candidate."""
            return (
                f"Create a local candidate for {repo!r} with claim {claim!r}. "
                "Use current source and evidence refs. This candidate contour "
                "may write only its allowlisted local memo ports and cannot "
                "accept durable memory."
            )

        @mcp.prompt(name="memo-review")
        def memo_review(candidate_path: str) -> str:
            """Prompt route for forwarding checks below durable review."""
            return (
                f"Use the read contour to validate {candidate_path!r}; then use "
                "this candidate contour only for an allowlisted export or "
                "forwarding-check receipt. MCP is not aoa-memo review."
            )

    _apply_capability_profile(
        mcp,
        policy_family=contour,
        workspace_root=workspace_root,
    )
    LOGGER.info("AoA memo MCP %s contour ready", contour)
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    contour = configured_policy_family()
    profile = _default_http_capability_profile(contour)
    if profile:
        os.environ[CAPABILITY_PROFILE_ENV_VAR] = profile
    _run_server(build_server(policy_family=contour))
