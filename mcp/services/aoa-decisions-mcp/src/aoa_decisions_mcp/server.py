from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

from ._http_auth import http_auth_config
from ._modern_runtime import run_server
from ._runtime_config import SERVICE_CONFIG
from .core import AoADecisionsMCPState
from .organ_access import CAPABILITY_ID
from .organ_access import load_organ_access_manifest
from .organ_access import validate_runtime_bindings

LOGGER = logging.getLogger(__name__)
SUPPORTED_CONTOURS = frozenset(SERVICE_CONFIG.contours)
CAPABILITY_PROFILE_ENV_VAR = "AOA_DECISIONS_MCP_CAPABILITY_PROFILE"
CAPABILITY_PROFILE_MAX_OUTPUT_BYTES = 32_768
CapabilityProfile = Literal["complete", "decision-retrieval"]
def _contour_http_auth_config(contour: str) -> Any:
    try:
        declared = SERVICE_CONFIG.contour(contour)
    except ValueError as exc:
        raise ValueError(
            f"unsupported decisions MCP contour {contour!r}; "
            f"expected one of {sorted(SUPPORTED_CONTOURS)}"
        ) from exc
    return http_auth_config(declared.port, **declared.auth.as_kwargs())


def configured_capability_profile(contour: str) -> CapabilityProfile:
    value = os.environ.get(CAPABILITY_PROFILE_ENV_VAR, "complete").strip()
    allowed = {"complete", CAPABILITY_ID} if contour == "read" else {"complete"}
    if value not in allowed:
        expected = ", ".join(sorted(allowed))
        raise SystemExit(
            f"{CAPABILITY_PROFILE_ENV_VAR} is incompatible with {contour}; "
            f"expected one of: {expected}"
        )
    return value  # type: ignore[return-value]


def _profile_freshness(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload.get(key)
        for key in (
            "status",
            "cache_status",
            "freshness_scope",
            "remote_freshness_checked",
            "input_fingerprint",
            "source_posture_status",
            "source_warning_repo_count",
        )
    }


def _profile_packet(payload: dict[str, Any]) -> dict[str, Any]:
    decisions = [
        {
            key: item.get(key)
            for key in ("label", "title", "status", "path", "source_sha256")
        }
        for item in payload.get("decisions", payload.get("matches", []))
        if isinstance(item, dict)
    ]
    result = {
        "schema": "aoa_decisions_retrieval_profile_result_v1",
        "decision_count": len(decisions),
        "decisions": decisions,
        "decision_views": list(payload.get("decision_views", [])),
        "freshness": _profile_freshness(payload.get("freshness", {})),
        "authority_note": payload.get("authority_note")
        or "Repo-local decision records own rationale; MCP is a navigation read model.",
        "claim_limits": payload.get("claim_limits", []),
        "max_output_bytes": CAPABILITY_PROFILE_MAX_OUTPUT_BYTES,
        "truncated": False,
    }
    while (
        len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode())
        > CAPABILITY_PROFILE_MAX_OUTPUT_BYTES
        and result["decision_views"]
    ):
        result["decision_views"].pop()
        result["decisions"].pop()
        result["decision_count"] = len(result["decisions"])
        result["truncated"] = True
    return result


def _run_server(server: Any, *, contour: str = "read") -> None:
    run_server(server, _contour_http_auth_config(contour))


def build_server(
    workspace_root: str | Path | None = None,
    stack_root: str | Path | None = None,
    output_dir: str | Path | None = None,
    contour: str = "read",
    capability_profile: CapabilityProfile | None = None,
) -> Any:
    try:
        from ._modern_runtime import ModernMCPServer  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'mcp'. Install with: python -m pip install -e ."
        ) from exc

    if contour not in SUPPORTED_CONTOURS:
        raise ValueError(
            f"unsupported decisions MCP contour {contour!r}; "
            f"expected one of {sorted(SUPPORTED_CONTOURS)}"
        )

    profile = capability_profile or configured_capability_profile(contour)
    allowed_profiles = {"complete", CAPABILITY_ID} if contour == "read" else {"complete"}
    if profile not in allowed_profiles:
        expected = ", ".join(sorted(allowed_profiles))
        raise SystemExit(
            f"aoa-decisions capability profile {profile!r} is incompatible with "
            f"{contour!r}; expected one of: {expected}"
        )

    mcp = ModernMCPServer(
        SERVICE_CONFIG.server_name(contour, profile),
        version=SERVICE_CONFIG.package_version,
        **_contour_http_auth_config(contour).server_kwargs,
    )
    read_only_tool = mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )

    def current_state() -> AoADecisionsMCPState:
        return AoADecisionsMCPState.discover(
            workspace_root=workspace_root,
            stack_root=stack_root,
            output_dir=output_dir,
            cache_write_allowed=contour == "internal_effect",
        )

    @read_only_tool
    def aoa_decisions_status() -> dict[str, Any]:
        """Inspect local cache readiness without creating or refreshing files."""
        return current_state().cache_posture()

    if contour == "read" and profile == CAPABILITY_ID:

        @read_only_tool
        def aoa_decisions_packet(
            query: str = "",
            repo: str | None = None,
            decision_id: str | None = None,
            path: str | None = None,
            limit: int = 12,
        ) -> dict[str, Any]:
            """Return compact owner-qualified decision matches from a fresh cache."""
            return _profile_packet(
                current_state().packet(
                    query=query,
                    repo=repo,
                    decision_id=decision_id,
                    path=path,
                    limit=min(max(limit, 1), 12),
                )
            )

        @read_only_tool
        def aoa_decisions_decision(
            decision_id: str, repo: str | None = None
        ) -> dict[str, Any]:
            """Return one exact owner-qualified decision neighborhood."""
            return _profile_packet(
                current_state().decision(decision_id=decision_id, repo=repo)
            )

        @mcp.resource("aoa-decisions://status")
        def status_resource() -> str:
            return json.dumps(
                current_state().cache_posture(), ensure_ascii=False, indent=2
            )

        @mcp.resource("aoa-decisions://decision/{decision_id}")
        def decision_resource(decision_id: str) -> str:
            return json.dumps(
                _profile_packet(current_state().decision(decision_id)),
                ensure_ascii=False,
                indent=2,
            )

        manifest = load_organ_access_manifest()
        validate_runtime_bindings(
            manifest,
            tool_names={
                "aoa_decisions_status",
                "aoa_decisions_packet",
                "aoa_decisions_decision",
            },
            resource_names={
                "aoa-decisions://status",
                "aoa-decisions://decision/{decision_id}",
            },
        )
        LOGGER.info(
            "AoA decisions MCP server ready: contour=%s profile=%s",
            contour,
            profile,
        )
        return mcp

    if contour == "internal_effect":

        @mcp.tool()
        def aoa_decisions_refresh(force: bool = False) -> dict[str, Any]:
            """Refresh the ignored local graph cache in the internal-effect contour."""
            return current_state().ensure_fresh(force=force)

    if contour == "read":

        @read_only_tool
        def aoa_decisions_summary() -> dict[str, Any]:
            """Return the existing locally fresh workspace decision graph summary."""
            return current_state().summary()

        @read_only_tool
        def aoa_decisions_search(
            query: str, repo: str | None = None, limit: int = 20
        ) -> dict[str, Any]:
            """Search the existing locally fresh graph and carry source warnings."""
            return current_state().search(query=query, repo=repo, limit=limit)

        @read_only_tool
        def aoa_decisions_packet(
            query: str = "",
            repo: str | None = None,
            decision_id: str | None = None,
            path: str | None = None,
            limit: int = 12,
        ) -> dict[str, Any]:
            """Return a compact locally fresh graph packet with explicit limits."""
            return current_state().packet(
                query=query,
                repo=repo,
                decision_id=decision_id,
                path=path,
                limit=limit,
            )

        @read_only_tool
        def aoa_decisions_repo(repo: str) -> dict[str, Any]:
            """Return a repo graph slice plus the checkout's local source posture."""
            return current_state().repo(repo)

        @read_only_tool
        def aoa_decisions_decision(
            decision_id: str, repo: str | None = None
        ) -> dict[str, Any]:
            """Return a locally fresh decision neighborhood."""
            return current_state().decision(decision_id=decision_id, repo=repo)

        @read_only_tool
        def aoa_decisions_source_surface(
            source_surface: str,
            repo: str | None = None,
            limit: int = 50,
        ) -> dict[str, Any]:
            """Return locally fresh decisions that cite a source surface."""
            return current_state().source_surface(
                source_surface=source_surface, repo=repo, limit=limit
            )

        @read_only_tool
        def aoa_decisions_owner_surface(
            owner_surface: str,
            repo: str | None = None,
            limit: int = 50,
        ) -> dict[str, Any]:
            """Return locally fresh decisions that own or guard an owner surface."""
            return current_state().owner_surface(
                owner_surface=owner_surface, repo=repo, limit=limit
            )

        @read_only_tool
        def aoa_decisions_changed_path(
            path: str,
            repo: str | None = None,
            limit: int = 50,
        ) -> dict[str, Any]:
            """Return locally fresh decisions likely impacted by a changed path."""
            return current_state().changed_path(path=path, repo=repo, limit=limit)

        @read_only_tool
        def aoa_decisions_repo_symmetry(repo: str | None = None) -> dict[str, Any]:
            """Return locally fresh decision-lane coverage without forced symmetry."""
            return current_state().repo_symmetry(repo=repo)

        @read_only_tool
        def aoa_decisions_issues(
            repo: str | None = None, limit: int = 100
        ) -> dict[str, Any]:
            """Return locally fresh graph issues and unknown-surface findings."""
            return current_state().issues(repo=repo, limit=limit)

        @mcp.resource("aoa-decisions://status")
        def status_resource() -> str:
            return json.dumps(
                current_state().cache_posture(), ensure_ascii=False, indent=2
            )

        @mcp.resource("aoa-decisions://summary")
        def summary_resource() -> str:
            return json.dumps(current_state().summary(), ensure_ascii=False, indent=2)

        @mcp.resource("aoa-decisions://repo/{repo}")
        def repo_resource(repo: str) -> str:
            return json.dumps(current_state().repo(repo), ensure_ascii=False, indent=2)

        @mcp.resource("aoa-decisions://decision/{decision_id}")
        def decision_resource(decision_id: str) -> str:
            return json.dumps(
                current_state().decision(decision_id), ensure_ascii=False, indent=2
            )

        @mcp.resource("aoa-decisions://issues")
        def issues_resource() -> str:
            return json.dumps(current_state().issues(), ensure_ascii=False, indent=2)

        @mcp.resource("aoa-decisions://issues/{repo}")
        def repo_issues_resource(repo: str) -> str:
            return json.dumps(
                current_state().issues(repo=repo), ensure_ascii=False, indent=2
            )

        @mcp.prompt(name="decision-find")
        def decision_find(query: str) -> str:
            """Prompt route for finding prior decision rationale."""
            return (
                f"Use aoa_decisions_packet(query={query!r}) first. "
                "Inspect its source warnings, then inspect the repo-local docs/decisions files named in the packet "
                "before making source-truth claims. A cache-fresh packet is not remote-fresh proof."
            )

        @mcp.prompt(name="decision-create")
        def decision_create(repo: str, intent: str) -> str:
            """Prompt route for creating a decision with prior graph context."""
            return (
                f"Use aoa_decisions_repo(repo={repo!r}) and "
                f"aoa_decisions_packet(query={intent!r}, repo={repo!r}) "
                "before choosing the next local decision id, template, source surfaces, and supersession links. "
                "If repo source_posture is not clean and aligned, derive the id and current rationale from the "
                "authoritative repo-local source rather than the workspace graph."
            )

    LOGGER.info(
        "AoA decisions MCP server ready: contour=%s profile=%s", contour, profile
    )
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    contour = os.environ.get("AOA_DECISIONS_MCP_CONTOUR", "read")
    _run_server(build_server(contour=contour), contour=contour)
