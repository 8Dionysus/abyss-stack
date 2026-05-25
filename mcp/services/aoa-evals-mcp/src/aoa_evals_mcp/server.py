from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .core import AoAEvalsMCPState


LOGGER = logging.getLogger(__name__)


def build_server(
    workspace_root: str | Path | None = None,
    evals_root: str | Path | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP("aoa-evals-mcp", json_response=True)

    def current_state() -> AoAEvalsMCPState:
        return AoAEvalsMCPState.discover(workspace_root=workspace_root, evals_root=evals_root)

    @mcp.tool()
    def aoa_evals_select(proof_question: str = "", filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Select bounded eval candidates from compact aoa-evals read models."""
        return current_state().select(proof_question=proof_question, filters=filters)

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
    def aoa_evals_report_skeleton(name: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
        """Prepare a candidate-only report skeleton without computing a verdict."""
        return current_state().report_skeleton(name=name, evidence_refs=evidence_refs)

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

    @mcp.resource("aoa-evals://reports")
    def reports_resource() -> str:
        return json.dumps(current_state().reports(), ensure_ascii=False, indent=2)

    @mcp.prompt(name="eval-select")
    def eval_select(proof_question: str) -> str:
        """Prompt route for choosing a bounded eval candidate."""
        return (
            f"Use aoa_evals_select(proof_question={proof_question!r}, filters={{}}), "
            "then inspect the selected bundle before interpreting evidence."
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
            f"Use aoa_evals_runtime_evidence_template(name={name!r}). "
            "Treat the result as candidate evidence until bundle-local review accepts it."
        )

    @mcp.prompt(name="report-skeleton")
    def report_skeleton(name: str) -> str:
        """Prompt route for preparing a bounded report skeleton."""
        return (
            f"Use aoa_evals_report_skeleton(name={name!r}, evidence_refs=[]). "
            "Leave verdict unset; MCP must not publish receipts or compute the result."
        )

    LOGGER.info("AoA evals MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_server().run(transport="stdio")
