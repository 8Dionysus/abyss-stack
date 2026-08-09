from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings
from .core import AoAEvalsMCPState
from .organ_access import DISCOVERY_CAPABILITY_ID
from .organ_access import PROOF_RESULT_CAPABILITY_ID
from .organ_access import REQUEST_CAPABILITY_ID
from .organ_access import load_owner_manifest
from .organ_access import validate_runtime_bindings


LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "aoa-evals-mcp"
APPLICATION_VERSION = "0.2.0"
READ_HTTP_PORT = 5424
CANDIDATE_HTTP_PORT = 5435
DEFAULT_HTTP_PORT = READ_HTTP_PORT
PolicyFamily = Literal["read", "candidate"]
CapabilityProfile = Literal[
    "complete",
    "eval-discovery-read",
    "eval-request-prepare",
    "proof-result-read",
]

READ_TOKEN_ENV_VAR = "AOA_EVALS_MCP_READ_BEARER_TOKEN"
READ_CREDENTIAL_NAME = "aoa-evals-mcp-read-bearer-token"
READ_AUTH_SCOPE = "mcp:aoa-evals:read"
READ_CLIENT_ID = "aoa-loopback-codex:aoa-evals:read"

CANDIDATE_TOKEN_ENV_VAR = "AOA_EVALS_MCP_CANDIDATE_BEARER_TOKEN"
CANDIDATE_CREDENTIAL_NAME = "aoa-evals-mcp-candidate-bearer-token"
CANDIDATE_AUTH_SCOPE = "mcp:aoa-evals:candidate"
CANDIDATE_CLIENT_ID = "aoa-loopback-codex:aoa-evals:candidate"


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


def configured_capability_profile(
    policy_family: PolicyFamily,
) -> CapabilityProfile:
    value = os.environ.get(
        "AOA_EVALS_MCP_CAPABILITY_PROFILE", "complete"
    ).strip()
    allowed = {
        "read": {"complete", DISCOVERY_CAPABILITY_ID, PROOF_RESULT_CAPABILITY_ID},
        "candidate": {"complete", REQUEST_CAPABILITY_ID},
    }
    if value not in allowed[policy_family]:
        expected = ", ".join(sorted(allowed[policy_family]))
        raise SystemExit(
            "AOA_EVALS_MCP_CAPABILITY_PROFILE is incompatible with "
            f"{policy_family}; expected one of: {expected}"
        )
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
    evals_root: str | Path | None = None,
    *,
    policy_family: PolicyFamily | None = None,
    capability_profile: CapabilityProfile | None = None,
) -> Any:
    try:
        from ._modern_runtime import AbyssMCPServer  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'mcp'. Install with: python -m pip install -e ."
        ) from exc

    contour = policy_family or configured_policy_family()
    profile = capability_profile or configured_capability_profile(contour)
    if profile != configured_capability_profile(contour):
        allowed = {
            "read": {"complete", DISCOVERY_CAPABILITY_ID, PROOF_RESULT_CAPABILITY_ID},
            "candidate": {"complete", REQUEST_CAPABILITY_ID},
        }
        if profile not in allowed[contour]:
            raise SystemExit(
                f"aoa-evals capability profile {profile!r} is incompatible with "
                f"{contour!r}"
            )
    mcp = AbyssMCPServer(
        f"aoa-evals-mcp-{contour}-{profile}",
        json_response=True,
        **_contour_http_auth_kwargs(contour),
    )
    _bind_server_info_version(mcp)
    read_only_tool = mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    candidate_tool = mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    candidate_prepare_tool = mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )

    def current_state() -> AoAEvalsMCPState:
        return AoAEvalsMCPState.discover(
            workspace_root=workspace_root,
            evals_root=evals_root,
        )

    if profile == DISCOVERY_CAPABILITY_ID:

        @read_only_tool
        def aoa_evals_select(
            proof_question: str = "",
            filters: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Select bounded eval candidates from compact owner read models."""
            return current_state().select(
                proof_question=proof_question,
                filters=filters,
            )

        @read_only_tool
        def aoa_evals_inspect(name: str) -> dict[str, Any]:
            """Inspect one eval bundle through generated readers and source refs."""
            return current_state().inspect_bundle(name)

        @read_only_tool
        def aoa_evals_expand(
            name: str,
            section_key: str | None = None,
        ) -> dict[str, Any]:
            """Expand one generated bundle section or list section keys."""
            return current_state().expand_bundle(
                name=name,
                section_key=section_key,
            )

        @read_only_tool
        def aoa_evals_runtime_status() -> dict[str, Any]:
            """Report source or approved-mirror freshness."""
            return current_state().runtime_status()

        @mcp.resource("aoa-evals://catalog")
        def catalog_resource() -> str:
            return json.dumps(
                current_state().build_catalog(), ensure_ascii=False, indent=2
            )

        @mcp.resource("aoa-evals://bundle/{name}")
        def bundle_resource(name: str) -> str:
            return json.dumps(
                current_state().inspect_bundle(name), ensure_ascii=False, indent=2
            )

        @mcp.resource("aoa-evals://bundle/{name}/sections")
        def bundle_sections_resource(name: str) -> str:
            return json.dumps(
                current_state().expand_bundle(name), ensure_ascii=False, indent=2
            )

        @mcp.resource("aoa-evals://runtime-status")
        def runtime_status_resource() -> str:
            return json.dumps(
                current_state().runtime_status(), ensure_ascii=False, indent=2
            )

        owner_manifest = load_owner_manifest(workspace_root, evals_root)
        validate_runtime_bindings(
            owner_manifest,
            capability_id=profile,
            tool_names={
                "aoa_evals_select",
                "aoa_evals_inspect",
                "aoa_evals_expand",
                "aoa_evals_runtime_status",
            },
            resource_templates={
                "aoa-evals://catalog",
                "aoa-evals://bundle/{name}",
                "aoa-evals://bundle/{name}/sections",
                "aoa-evals://runtime-status",
            },
        )
        LOGGER.info("AoA evals MCP %s profile ready", profile)
        return mcp

    if profile == PROOF_RESULT_CAPABILITY_ID:

        @read_only_tool
        def aoa_evals_read_proof_result(report_id: str) -> dict[str, Any]:
            """Read one already issued source report without issuing proof."""
            return current_state().read_proof_result(report_id)

        @mcp.resource("aoa-evals://proof-result/{report_id}")
        def proof_result_resource(report_id: str) -> str:
            return json.dumps(
                current_state().read_proof_result(report_id),
                ensure_ascii=False,
                indent=2,
            )

        owner_manifest = load_owner_manifest(workspace_root, evals_root)
        validate_runtime_bindings(
            owner_manifest,
            capability_id=profile,
            tool_names={"aoa_evals_read_proof_result"},
            resource_templates={"aoa-evals://proof-result/{report_id}"},
        )
        LOGGER.info("AoA evals MCP %s profile ready", profile)
        return mcp

    if profile == REQUEST_CAPABILITY_ID:

        @candidate_prepare_tool
        def aoa_evals_prepare_request_candidate(
            proof_question: str = "",
            proposal: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Prepare one typed, non-persistent eval request candidate."""
            return current_state().prepare_request_candidate(
                proof_question=proof_question,
                proposal=proposal,
            )

        owner_manifest = load_owner_manifest(workspace_root, evals_root)
        validate_runtime_bindings(
            owner_manifest,
            capability_id=profile,
            tool_names={"aoa_evals_prepare_request_candidate"},
            resource_templates=set(),
        )
        LOGGER.info("AoA evals MCP %s profile ready", profile)
        return mcp

    if contour == "read":

        @read_only_tool
        def aoa_evals_select(
            proof_question: str = "",
            filters: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Select bounded eval candidates from compact aoa-evals read models."""
            return current_state().select(
                proof_question=proof_question,
                filters=filters,
            )

        @read_only_tool
        def aoa_evals_find_or_propose(
            proof_question: str = "",
            proposal: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Find eval routes or shape a non-persistent eval_need_v1 context."""
            return current_state().find_or_propose(
                proof_question=proof_question,
                proposal=proposal,
            )

        @read_only_tool
        def aoa_evals_inspect(name: str) -> dict[str, Any]:
            """Inspect one eval bundle through generated readers and source refs."""
            return current_state().inspect_bundle(name)

        @read_only_tool
        def aoa_evals_expand(
            name: str,
            section_key: str | None = None,
        ) -> dict[str, Any]:
            """Expand one generated bundle section or list generated sections."""
            return current_state().expand_bundle(
                name=name,
                section_key=section_key,
            )

        @read_only_tool
        def aoa_evals_comparison(
            baseline_mode: str | None = None,
        ) -> dict[str, Any]:
            """Read comparison-spine records filtered by baseline mode."""
            return current_state().comparison(baseline_mode=baseline_mode)

        @read_only_tool
        def aoa_evals_runtime_evidence_template(
            name: str,
        ) -> dict[str, Any]:
            """Return candidate-only evidence templates without persistence."""
            return current_state().runtime_evidence_template(name)

        @read_only_tool
        def aoa_evals_runtime_status() -> dict[str, Any]:
            """Report source/mirror freshness and required reader presence."""
            return current_state().runtime_status()

        @read_only_tool
        def aoa_evals_forge_access_packet() -> dict[str, Any]:
            """Return the read-only Eval Forge front-door/access packet."""
            return current_state().eval_forge_access_packet()

        @read_only_tool
        def aoa_evals_validate_evidence_candidate(
            packet: dict[str, Any],
        ) -> dict[str, Any]:
            """Validate candidate evidence shape without persisting or accepting it."""
            return current_state().validate_evidence_candidate(packet)

        @read_only_tool
        def aoa_evals_runtime_candidate_exports(
            limit: int = 20,
        ) -> dict[str, Any]:
            """List stack-owned private runtime candidate exports."""
            return current_state().runtime_candidate_exports(limit=limit)

        @read_only_tool
        def aoa_evals_read_runtime_candidate_export(
            record_id: str,
            include_payload: bool = False,
        ) -> dict[str, Any]:
            """Read one runtime candidate export for review routing."""
            return current_state().read_runtime_candidate_export(
                record_id=record_id,
                include_payload=include_payload,
            )

        @read_only_tool
        def aoa_evals_report_skeleton(
            name: str,
            evidence_refs: list[str] | None = None,
        ) -> dict[str, Any]:
            """Prepare a non-persistent report skeleton without a verdict."""
            return current_state().report_skeleton(
                name=name,
                evidence_refs=evidence_refs,
            )

        @read_only_tool
        def aoa_evals_local_ports(
            status: str | None = None,
            include_skeleton: bool = True,
        ) -> dict[str, Any]:
            """List workspace repo-local eval ports and validation summaries."""
            return current_state().local_ports(
                status=status,
                include_skeleton=include_skeleton,
            )

        @read_only_tool
        def aoa_evals_local_port(repo: str) -> dict[str, Any]:
            """Inspect one repo-local eval port."""
            return current_state().local_port(repo=repo)

        @read_only_tool
        def aoa_evals_find_or_propose_local(
            repo: str,
            proof_question: str = "",
            proposal: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Prepare a non-persistent local eval_need write plan."""
            return current_state().find_or_propose_local(
                repo=repo,
                proof_question=proof_question,
                proposal=proposal,
            )

        @mcp.resource("aoa-evals://catalog")
        def catalog_resource() -> str:
            return json.dumps(
                current_state().build_catalog(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://bundle/{name}")
        def bundle_resource(name: str) -> str:
            return json.dumps(
                current_state().inspect_bundle(name),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://bundle/{name}/sections")
        def bundle_sections_resource(name: str) -> str:
            return json.dumps(
                current_state().expand_bundle(name),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://comparison-spine")
        def comparison_spine_resource() -> str:
            return json.dumps(
                current_state().comparison(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://runtime-candidate-templates")
        def runtime_candidate_templates_resource() -> str:
            return json.dumps(
                current_state().runtime_candidate_templates_resource(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://runtime-status")
        def runtime_status_resource() -> str:
            return json.dumps(
                current_state().runtime_status(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://forge-access")
        def forge_access_resource() -> str:
            return json.dumps(
                current_state().eval_forge_access_packet(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://runtime-evidence/schema")
        def runtime_evidence_schema_resource() -> str:
            return json.dumps(
                current_state().runtime_evidence_schema_resource(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://runtime-candidate-exports")
        def runtime_candidate_exports_resource() -> str:
            return json.dumps(
                current_state().runtime_candidate_exports(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://runtime-candidate-export/{record_id}")
        def runtime_candidate_export_resource(record_id: str) -> str:
            return json.dumps(
                current_state().read_runtime_candidate_export(record_id),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://reports")
        def reports_resource() -> str:
            return json.dumps(
                current_state().reports(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://local-ports")
        def local_ports_resource() -> str:
            return json.dumps(
                current_state().local_ports(),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://local-port/{repo}")
        def local_port_resource(repo: str) -> str:
            return json.dumps(
                current_state().local_port(repo),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://local-port/{repo}/intake")
        def local_port_intake_resource(repo: str) -> str:
            return json.dumps(
                current_state().read_resource(
                    f"aoa-evals://local-port/{repo}/intake"
                ),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://local-port/{repo}/suites")
        def local_port_suites_resource(repo: str) -> str:
            return json.dumps(
                current_state().read_resource(
                    f"aoa-evals://local-port/{repo}/suites"
                ),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.resource("aoa-evals://local-port/{repo}/reports")
        def local_port_reports_resource(repo: str) -> str:
            return json.dumps(
                current_state().read_resource(
                    f"aoa-evals://local-port/{repo}/reports"
                ),
                ensure_ascii=False,
                indent=2,
            )

        @mcp.prompt(name="eval-select")
        def eval_select(proof_question: str) -> str:
            """Prompt route for choosing a bounded eval candidate."""
            return (
                f"Use aoa_evals_select(proof_question={proof_question!r}, "
                "filters={}), then inspect the selected source bundle."
            )

        @mcp.prompt(name="eval-find-or-propose")
        def eval_find_or_propose(proof_question: str) -> str:
            """Prompt route for route-first eval growth."""
            return (
                f"Use aoa_evals_find_or_propose("
                f"proof_question={proof_question!r}, proposal={{}}). "
                "Treat any new eval_need packet as non-persistent candidate context."
            )

        @mcp.prompt(name="eval-forge-access")
        def eval_forge_access() -> str:
            """Prompt route for starting from the Eval Forge front door."""
            return (
                "Use aoa_evals_forge_access_packet() first. Treat its routes as "
                "access evidence only; proof authority and promotion stay outside MCP."
            )

        @mcp.prompt(name="eval-review")
        def eval_review(name: str) -> str:
            """Prompt route for reviewing one eval bundle."""
            return (
                f"Use aoa_evals_inspect(name={name!r}) and "
                f"aoa_evals_expand(name={name!r}, section_key=None), then read "
                "the source bundle before interpreting proof."
            )

        @mcp.prompt(name="evidence-packet")
        def evidence_packet(name: str) -> str:
            """Prompt route for shaping candidate evidence."""
            return (
                f"Use aoa_evals_runtime_evidence_template(name={name!r}), then "
                "validate candidate shape. Treat every result as candidate evidence."
            )

        @mcp.prompt(name="report-skeleton")
        def report_skeleton(name: str) -> str:
            """Prompt route for preparing a bounded report skeleton."""
            return (
                f"Use aoa_evals_report_skeleton(name={name!r}, "
                "evidence_refs=[]). Leave verdict unset."
            )

        @mcp.prompt(name="local-eval-port")
        def local_eval_port(repo: str, proof_question: str) -> str:
            """Prompt route for local eval-port discovery and write planning."""
            return (
                f"Use aoa_evals_local_port(repo={repo!r}) and "
                f"aoa_evals_find_or_propose_local(repo={repo!r}, "
                f"proof_question={proof_question!r}, proposal={{}}). "
                "Carry an accepted plan to the separately authenticated candidate contour."
            )

    else:

        @candidate_tool
        def aoa_evals_write_local_intake(
            repo: str,
            packet: dict[str, Any],
            file_slug: str | None = None,
            apply: bool = False,
            replace_existing: bool = False,
        ) -> dict[str, Any]:
            """Dry-run or write one allowlisted repo-local eval intake packet."""
            return current_state().write_local_intake(
                repo=repo,
                packet=packet,
                file_slug=file_slug,
                apply=apply,
                replace_existing=replace_existing,
            )

        @candidate_tool
        def aoa_evals_write_local_suite_note(
            repo: str,
            suite_slug: str,
            title: str,
            summary: str,
            body_markdown: str,
            refs: list[str] | None = None,
            apply: bool = False,
            replace_existing: bool = False,
        ) -> dict[str, Any]:
            """Dry-run or write one allowlisted repo-local suite note."""
            return current_state().write_local_suite_note(
                repo=repo,
                suite_slug=suite_slug,
                title=title,
                summary=summary,
                body_markdown=body_markdown,
                refs=refs,
                apply=apply,
                replace_existing=replace_existing,
            )

        @candidate_tool
        def aoa_evals_write_local_report_note(
            repo: str,
            report_slug: str,
            title: str,
            summary: str,
            body_markdown: str,
            refs: list[str] | None = None,
            apply: bool = False,
            replace_existing: bool = False,
        ) -> dict[str, Any]:
            """Dry-run or write one allowlisted repo-local report note."""
            return current_state().write_local_report_note(
                repo=repo,
                report_slug=report_slug,
                title=title,
                summary=summary,
                body_markdown=body_markdown,
                refs=refs,
                apply=apply,
                replace_existing=replace_existing,
            )

        @mcp.prompt(name="local-eval-port-write")
        def local_eval_port_write(repo: str) -> str:
            """Prompt route for a reviewed local eval-port write plan."""
            return (
                f"Use this contour only after inspecting {repo!r} through the "
                "read endpoint. Keep apply=false for the first call. apply=true "
                "may write only the configured local intake/suite/report allowlist "
                "and cannot accept proof."
            )

    LOGGER.info("AoA evals MCP %s contour ready", contour)
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _run_server(build_server())
