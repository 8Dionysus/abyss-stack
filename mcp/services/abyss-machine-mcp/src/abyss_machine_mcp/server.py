from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings
from .core import AbyssMachineMCPState, CommandRunner


LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "abyss-machine-mcp"
APPLICATION_VERSION = "0.2.0"
DEFAULT_HTTP_PORT = 5423
READ_AUTH = {
    "token_env_var": "ABYSS_MACHINE_MCP_READ_BEARER_TOKEN",
    "credential_name": "abyss-machine-mcp-read-bearer-token",
    "auth_scope": "mcp:abyss-machine:read",
    "client_id": "aoa-loopback-codex:abyss-machine:read",
}


def _application_version() -> str:
    return APPLICATION_VERSION


def _bind_server_info_version(mcp: Any) -> None:
    low_level_server = getattr(mcp, "_mcp_server", None)
    if low_level_server is None or not hasattr(low_level_server, "version"):
        raise RuntimeError(
            "the pinned MCP SDK no longer exposes the server identity seam"
        )
    low_level_server.version = _application_version()


def _read_http_auth_kwargs() -> dict[str, Any]:
    return _http_auth_kwargs(DEFAULT_HTTP_PORT, **READ_AUTH)


def _run_server(server: Any) -> None:
    settings = _transport_settings(DEFAULT_HTTP_PORT)
    _read_http_auth_kwargs()
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    assert settings.host is not None
    assert settings.port is not None
    server.configure_http(settings.host, settings.port)
    server.run(transport="streamable-http")


def build_server(
    workspace_root: str | Path | None = None,
    abyss_machine_bin: str | None = None,
    command_runner: CommandRunner | None = None,
    timeout_seconds: float | None = None,
) -> Any:
    try:
        from ._modern_runtime import AbyssMCPServer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = AbyssMCPServer(
        "abyss-machine-mcp-read",
        json_response=True,
        **_read_http_auth_kwargs(),
    )
    _bind_server_info_version(mcp)

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
        axis: str = "",
        reader_profile: str = "agent",
        limit: int = 20,
        evidence_limit: int = 12,
        artifact_class: str = "",
        consumer_intent: str = "agent",
        source_repo: str = "",
        source_ref: str = "",
        source_root: str = "",
    ) -> dict[str, Any]:
        """Read one allowlisted abyss-machine surface as compact typed JSON."""
        return current_state().surface(
            name,
            query=query,
            work_class=work_class,
            kind=kind,
            scope=scope,
            mode=mode,
            axis=axis,
            reader_profile=reader_profile,
            limit=limit,
            evidence_limit=evidence_limit,
            artifact_class=artifact_class,
            consumer_intent=consumer_intent,
            source_repo=source_repo,
            source_ref=source_ref,
            source_root=source_root,
        )

    @mcp.tool()
    def abyss_machine_surfaces() -> dict[str, Any]:
        """List the finite read contour and the effectful routes it withdraws."""
        return current_state().available_surfaces()

    @mcp.tool()
    def abyss_machine_evidence_map(layer: str | None = None, limit: int = 40) -> dict[str, Any]:
        """Return compact evidence refs from the stack bridge."""
        return current_state().evidence_map(layer=layer, limit=limit)

    @mcp.tool()
    def abyss_machine_route(intent: str, work_class: str = "heavy", kind: str = "ai") -> dict[str, Any]:
        """Plan a non-mutating owner-aware route before starting work."""
        return current_state().machine_route(intent=intent, work_class=work_class, kind=kind)

    @mcp.tool()
    def abyss_machine_maps(axis: str = "", query: str = "", limit: int = 40) -> dict[str, Any]:
        """Query the generated machine atlas maps as route signals."""
        return current_state().machine_maps(axis=axis or None, query=query, limit=limit)

    @mcp.tool()
    def abyss_machine_context_packet(
        axis: str = "",
        query: str = "",
        reader_profile: str = "agent",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return a bounded machine atlas context packet for a reader profile."""
        return current_state().machine_context_packet(axis=axis or None, query=query, reader_profile=reader_profile, limit=limit)

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

    @mcp.resource("abyss-machine://memory-pressure")
    def memory_pressure_resource() -> str:
        return json.dumps(current_state().surface("memory-pressure"), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://typing-status")
    def typing_status_resource() -> str:
        return json.dumps(current_state().surface("typing-status"), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://maps")
    def maps_resource() -> str:
        return json.dumps(current_state().machine_maps(limit=20), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://maps/{axis}")
    def maps_axis_resource(axis: str) -> str:
        return json.dumps(current_state().machine_maps(axis=axis, limit=20), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://context-packet/{reader_profile}")
    def context_packet_resource(reader_profile: str) -> str:
        return json.dumps(current_state().machine_context_packet(reader_profile=reader_profile, limit=20), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://rag")
    def rag_resource() -> str:
        return json.dumps(current_state().surface("rag-latest"), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://surfaces")
    def surfaces_resource() -> str:
        return json.dumps(current_state().available_surfaces(), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://processes-latest")
    def processes_latest_resource() -> str:
        return json.dumps(current_state().surface("processes-latest"), ensure_ascii=False, indent=2)

    @mcp.resource("abyss-machine://changes-latest")
    def changes_latest_resource() -> str:
        return json.dumps(current_state().surface("changes-latest"), ensure_ascii=False, indent=2)

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

    @mcp.prompt(name="machine-atlas")
    def machine_atlas(intent: str) -> str:
        """Prompt route for using machine atlas maps."""
        return (
            f"For intent {intent!r}, use abyss_machine_maps(axis='', query=<focused term>, limit=20) first. "
            "For boundary context, inspect axes by-eval-packet, by-memory-candidate, by-rag-run, and by-kag-export. "
            "Use abyss_machine_context_packet(axis=<axis>, reader_profile=<profile>, limit=20). "
            "Treat entries and packets as route signals, not destinations, source truth, or permission to act."
        )

    @mcp.prompt(name="artifact-trust-read")
    def artifact_trust_read(artifact_class: str) -> str:
        """Prompt route for read-only artifact trust orientation."""
        return (
            "Use abyss_machine_surface(name='artifact-trust-registry-latest', "
            f"artifact_class={artifact_class!r}), then read artifact-trust-gate for the same class. "
            "The read contour does not refresh requirements, affected, coverage, scenario, or validation artifacts. "
            "Run those effectful diagnostics only through the owning abyss-machine CLI route. Treat MCP output as "
            "read-only evidence; build, sign, promote, or repair only through the owner."
        )

    @mcp.prompt(name="host-incident-triage")
    def host_incident_triage(symptom: str) -> str:
        """Prompt route for host incident orientation."""
        return (
            f"Use abyss_machine_brief(profile='live') for symptom {symptom!r}, then inspect "
            "abyss_machine_surfaces() before selecting a targeted read surface. Run refreshes and "
            "validators outside MCP through abyss-machine."
        )

    LOGGER.info("Abyss Machine MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _run_server(build_server())
