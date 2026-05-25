from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .core import AbyssMachineMCPState, CommandRunner


LOGGER = logging.getLogger(__name__)


def build_server(
    workspace_root: str | Path | None = None,
    abyss_machine_bin: str | None = None,
    command_runner: CommandRunner | None = None,
    timeout_seconds: float | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP("abyss-machine-mcp", json_response=True)

    def current_state() -> AbyssMachineMCPState:
        return AbyssMachineMCPState.discover(
            workspace_root=workspace_root,
            abyss_machine_bin=abyss_machine_bin,
            command_runner=command_runner,
            timeout_seconds=timeout_seconds,
        )

    @mcp.tool()
    def abyss_machine_brief(profile: str = "fast", evidence_limit: int = 8) -> dict[str, Any]:
        """Return compact owner-aware machine context."""
        return current_state().machine_brief(profile=profile, evidence_limit=evidence_limit)

    @mcp.tool()
    def abyss_machine_surface(
        name: str,
        query: str = "",
        work_class: str = "heavy",
        kind: str = "ai",
        scope: str = "now",
        mode: str = "hybrid",
    ) -> dict[str, Any]:
        """Read one allowlisted abyss-machine surface as compact typed JSON."""
        return current_state().surface(
            name,
            query=query,
            work_class=work_class,
            kind=kind,
            scope=scope,
            mode=mode,
        )

    @mcp.tool()
    def abyss_machine_evidence_map(layer: str | None = None, limit: int = 40) -> dict[str, Any]:
        """Return compact evidence refs from the stack bridge."""
        return current_state().evidence_map(layer=layer, limit=limit)

    @mcp.tool()
    def abyss_machine_route(intent: str, work_class: str = "heavy", kind: str = "ai") -> dict[str, Any]:
        """Plan a non-mutating owner-aware route before starting work."""
        return current_state().machine_route(intent=intent, work_class=work_class, kind=kind)

    @mcp.tool()
    def abyss_machine_recall(query: str, mode: str = "hybrid") -> dict[str, Any]:
        """Run focused nervous recall as evidence, not operator intent."""
        return current_state().recall(query=query, mode=mode)

    @mcp.resource("abyss-machine://brief")
    def brief_resource() -> str:
        return json.dumps(current_state().machine_brief(), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://authority")
    def authority_resource() -> str:
        return json.dumps(current_state().authority_boundary(), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://evidence-map")
    def evidence_map_resource() -> str:
        return json.dumps(current_state().evidence_map(), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://stack-bridge")
    def stack_bridge_resource() -> str:
        return json.dumps(current_state().surface("stack-bridge"), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://resource-status")
    def resource_status_resource() -> str:
        return json.dumps(current_state().surface("resource-status"), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://memory-pressure")
    def memory_pressure_resource() -> str:
        return json.dumps(current_state().surface("memory-pressure"), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://typing-status")
    def typing_status_resource() -> str:
        return json.dumps(current_state().surface("typing-status"), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://surface/{name}")
    def surface_resource(name: str) -> str:
        return json.dumps(current_state().surface(name), ensure_ascii=False, indent=2)

    @mcp.prompt(name="machine-brief")
    def machine_brief() -> str:
        """Prompt route for obtaining the compact machine map."""
        return (
            "Use abyss_machine_brief(profile='fast') first. Read owner_layers, "
            "constraints, safe_next_route, and the first evidence refs before acting. "
            "Use abyss_machine_evidence_map(limit=N) when more refs are needed."
        )

    @mcp.prompt(name="before-heavy-work")
    def before_heavy_work(intent: str) -> str:
        """Prompt route before starting medium or heavy host work."""
        return (
            f"Use abyss_machine_route(intent={intent!r}, work_class='heavy', kind='ai'). "
            "Treat the result as preflight evidence only; it does not authorize mutation."
        )

    @mcp.prompt(name="typing-context")
    def typing_context() -> str:
        """Prompt route for typed-text intake posture."""
        return (
            "Use abyss_machine_surface(name='typing-status') and "
            "abyss_machine_surface(name='typing-causal-context'). "
            "Do not request raw private captures unless the operator explicitly authorizes it."
        )

    @mcp.prompt(name="nervous-recall")
    def nervous_recall(query: str) -> str:
        """Prompt route for focused host recall."""
        return (
            f"Use abyss_machine_recall(query={query!r}, mode='hybrid'). "
            "Treat returned items as evidence and verify source refs before making claims."
        )

    @mcp.prompt(name="host-incident-triage")
    def host_incident_triage(symptom: str) -> str:
        """Prompt route for host incident orientation."""
        return (
            f"Use abyss_machine_brief(profile='live') for symptom {symptom!r}, then read the targeted "
            "surface named by the failing subsystem. Use abyss-machine validators outside MCP for confirmation."
        )

    LOGGER.info("Abyss Machine MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_server().run(transport="stdio")
