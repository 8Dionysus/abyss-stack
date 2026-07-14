from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings
from .core import AoAEvalsMCPState


LOGGER = logging.getLogger(__name__)
DEFAULT_HTTP_PORT = 5424


def _run_server(server: Any) -> None:
    settings = _transport_settings(DEFAULT_HTTP_PORT)
    _http_auth_kwargs(DEFAULT_HTTP_PORT)
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    assert settings.host is not None
    assert settings.port is not None
    server.settings.host = settings.host
    server.settings.port = settings.port
    server.run(transport="streamable-http")


def build_server(
    workspace_root: str | Path | None = None,
    evals_root: str | Path | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP("aoa-evals-mcp", json_response=True, **_http_auth_kwargs(DEFAULT_HTTP_PORT))

    def current_state() -> AoAEvalsMCPState:
        return AoAEvalsMCPState.discover(workspace_root=workspace_root, evals_root=evals_root)

    @mcp.tool()
    def aoa_evals_select(proof_question: str = "", filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Select bounded eval candidates from compact aoa-evals read models."""
        return current_state().select(proof_question=proof_question, filters=filters)

    @mcp.tool()
    def aoa_evals_find_or_propose(
        proof_question: str = "",
        proposal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Find existing eval routes or shape a read-only eval_need_v1 proposal context."""
        return current_state().find_or_propose(proof_question=proof_question, proposal=proposal)

    @mcp.tool()
    def aoa_evals_inspect(name: str) -> dict[str, Any]:
        """Inspect one eval bundle through catalog, capsule, reports, and source refs."""
        return current_state().inspect_bundle(name)

    @mcp.tool()
    def aoa_evals_expand(name: str, section_key: str | None = None) -> dict[str, Any]:
        """Expand one generated bundle section or list all generated sections."""
        return current_state().expand_bundle(name=name, section_key=section_key)

    @mcp.tool()
    def aoa_evals_comparison(baseline_mode: str | None = None) -> dict[str, Any]:
        """Read comparison-spine records, optionally filtered by baseline mode."""
        return current_state().comparison(baseline_mode=baseline_mode)

    @mcp.tool()
    def aoa_evals_runtime_evidence_template(name: str) -> dict[str, Any]:
        """Return candidate-only runtime evidence or artifact hook templates."""
        return current_state().runtime_evidence_template(name)

    @mcp.tool()
    def aoa_evals_runtime_status() -> dict[str, Any]:
        """Report source/mirror freshness and required reader presence."""
        return current_state().runtime_status()

    @mcp.tool()
    def aoa_evals_forge_access_packet() -> dict[str, Any]:
        """Return the read-only Eval Forge front-door/access packet."""
        return current_state().eval_forge_access_packet()

    @mcp.tool()
    def aoa_evals_validate_evidence_candidate(packet: dict[str, Any]) -> dict[str, Any]:
        """Validate a candidate evidence packet without ingesting or accepting it."""
        return current_state().validate_evidence_candidate(packet)

    @mcp.tool()
    def aoa_evals_runtime_candidate_exports(limit: int = 20) -> dict[str, Any]:
        """List stack-owned private runtime candidate exports without accepting evidence."""
        return current_state().runtime_candidate_exports(limit=limit)

    @mcp.tool()
    def aoa_evals_read_runtime_candidate_export(
        record_id: str,
        include_payload: bool = False,
    ) -> dict[str, Any]:
        """Read one stack-owned runtime candidate export as candidate-only evidence."""
        return current_state().read_runtime_candidate_export(record_id=record_id, include_payload=include_payload)

    @mcp.tool()
    def aoa_evals_report_skeleton(name: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
        """Prepare a candidate-only report skeleton without computing a verdict."""
        return current_state().report_skeleton(name=name, evidence_refs=evidence_refs)

    @mcp.tool()
    def aoa_evals_local_ports(status: str | None = None, include_skeleton: bool = True) -> dict[str, Any]:
        """List workspace repo-local eval ports and validation summaries."""
        return current_state().local_ports(status=status, include_skeleton=include_skeleton)

    @mcp.tool()
    def aoa_evals_local_port(repo: str) -> dict[str, Any]:
        """Inspect one repo-local eval port."""
        return current_state().local_port(repo=repo)

    @mcp.tool()
    def aoa_evals_find_or_propose_local(
        repo: str,
        proof_question: str = "",
        proposal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Find central routes and prepare a local eval_need write plan."""
        return current_state().find_or_propose_local(repo=repo, proof_question=proof_question, proposal=proposal)

    @mcp.tool()
    def aoa_evals_write_local_intake(
        repo: str,
        packet: dict[str, Any],
        file_slug: str | None = None,
        apply: bool = False,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        """Dry-run or write one repo-local eval_need_v1 intake packet."""
        return current_state().write_local_intake(
            repo=repo,
            packet=packet,
            file_slug=file_slug,
            apply=apply,
            replace_existing=replace_existing,
        )

    @mcp.tool()
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
        """Dry-run or write one repo-local suite note."""
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

    @mcp.tool()
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
        """Dry-run or write one repo-local report note."""
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

    @mcp.resource("aoa-evals://catalog")
    def catalog_resource() -> str:
        return json.dumps(current_state().build_catalog(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://bundle/{name}")
    def bundle_resource(name: str) -> str:
        return json.dumps(current_state().inspect_bundle(name), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://bundle/{name}/sections")
    def bundle_sections_resource(name: str) -> str:
        return json.dumps(current_state().expand_bundle(name), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://comparison-spine")
    def comparison_spine_resource() -> str:
        return json.dumps(current_state().comparison(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://runtime-candidate-templates")
    def runtime_candidate_templates_resource() -> str:
        return json.dumps(current_state().runtime_candidate_templates_resource(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://runtime-status")
    def runtime_status_resource() -> str:
        return json.dumps(current_state().runtime_status(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://forge-access")
    def forge_access_resource() -> str:
        return json.dumps(current_state().eval_forge_access_packet(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://runtime-evidence/schema")
    def runtime_evidence_schema_resource() -> str:
        return json.dumps(current_state().runtime_evidence_schema_resource(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://runtime-candidate-exports")
    def runtime_candidate_exports_resource() -> str:
        return json.dumps(current_state().runtime_candidate_exports(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://runtime-candidate-export/{record_id}")
    def runtime_candidate_export_resource(record_id: str) -> str:
        return json.dumps(current_state().read_runtime_candidate_export(record_id), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://reports")
    def reports_resource() -> str:
        return json.dumps(current_state().reports(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://local-ports")
    def local_ports_resource() -> str:
        return json.dumps(current_state().local_ports(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://local-port/{repo}")
    def local_port_resource(repo: str) -> str:
        return json.dumps(current_state().local_port(repo), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://local-port/{repo}/intake")
    def local_port_intake_resource(repo: str) -> str:
        return json.dumps(current_state().read_resource(f"aoa-evals://local-port/{repo}/intake"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://local-port/{repo}/suites")
    def local_port_suites_resource(repo: str) -> str:
        return json.dumps(current_state().read_resource(f"aoa-evals://local-port/{repo}/suites"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-evals://local-port/{repo}/reports")
    def local_port_reports_resource(repo: str) -> str:
        return json.dumps(current_state().read_resource(f"aoa-evals://local-port/{repo}/reports"), ensure_ascii=False, indent=2)

    @mcp.prompt(name="eval-select")
    def eval_select(proof_question: str) -> str:
        """Prompt route for choosing a bounded eval candidate."""
        return (
            f"Use aoa_evals_select(proof_question={proof_question!r}, filters={{}}), "
            "then inspect the selected bundle before interpreting evidence."
        )

    @mcp.prompt(name="eval-find-or-propose")
    def eval_find_or_propose(proof_question: str) -> str:
        """Prompt route for route-first eval growth."""
        return (
            f"Use aoa_evals_find_or_propose(proof_question={proof_question!r}, proposal={{}}). "
            "Inspect existing matches first. If a new eval is still needed, carry only the returned "
            "eval_need_v1 packet into the repo-local scaffold helper; MCP must not write source."
        )

    @mcp.prompt(name="eval-forge-access")
    def eval_forge_access() -> str:
        """Prompt route for starting from the Eval Forge front door."""
        return (
            "Use aoa_evals_forge_access_packet() or read aoa-evals://forge-access first. "
            "Treat Forge refs, candidate queue routes, local-port inventory, and MCP data as access-plane "
            "routing evidence only; proof authority, promotion, verdicts, and bundle writes stay outside MCP."
        )

    @mcp.prompt(name="eval-review")
    def eval_review(name: str) -> str:
        """Prompt route for reviewing one eval bundle."""
        return (
            f"Use aoa_evals_inspect(name={name!r}) and aoa_evals_expand(name={name!r}, section_key=None). "
            "Read the source bundle before claiming verdict meaning."
        )

    @mcp.prompt(name="evidence-packet")
    def evidence_packet(name: str) -> str:
        """Prompt route for shaping candidate evidence."""
        return (
            f"Use aoa_evals_runtime_evidence_template(name={name!r}), then "
            "aoa_evals_validate_evidence_candidate(packet={...}). "
            "Use aoa_evals_runtime_candidate_exports(limit=...) when stack-owned runtime exports already exist. "
            "Treat every result as candidate evidence until bundle-local review accepts it."
        )

    @mcp.prompt(name="report-skeleton")
    def report_skeleton(name: str) -> str:
        """Prompt route for preparing a bounded report skeleton."""
        return (
            f"Use aoa_evals_report_skeleton(name={name!r}, evidence_refs=[]). "
            "Leave verdict unset; MCP must not publish receipts or compute the result."
        )

    @mcp.prompt(name="local-eval-port")
    def local_eval_port(repo: str, proof_question: str) -> str:
        """Prompt route for local eval-port discovery and gated authoring."""
        return (
            f"Use aoa_evals_local_port(repo={repo!r}) and "
            f"aoa_evals_find_or_propose_local(repo={repo!r}, proof_question={proof_question!r}, proposal={{}}). "
            "Use write tools with apply=false first. Local writes stay below central proof authority."
        )

    LOGGER.info("AoA evals MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _run_server(build_server())
