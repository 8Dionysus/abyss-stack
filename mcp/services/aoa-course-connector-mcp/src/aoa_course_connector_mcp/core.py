"""Read-only adapter over the owner course connector MCP dispatcher."""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SERVICE_NAME = "aoa-course-connector-mcp"
DEFAULT_CONNECTOR_REPO = Path("/srv/AbyssOS/connectors/aoa-course-connector")
MAX_QUERY_LENGTH = 1000
MAX_LIMIT = 20
OWNER_READ_TOOLS = frozenset(
    {
        "connector_readiness",
        "evidence_report",
        "freshness_report",
        "graph_neighbors",
        "lesson_context",
        "list_sources",
        "source_answer",
        "sources_answer",
    }
)
EXCLUDED_OWNER_TOOLS = frozenset(
    {
        "connected_run",
        "browser_snapshot_audit",
        "connection_profile_run_plan",
        "connected_source_plan",
        "live_preflight",
        "refresh_plan",
        "semantic_provider_preflight",
    }
)
OwnerCall = Callable[[str, dict[str, object]], dict[str, object]]
OWNER_RESULT_SCHEMA = "aoa_course_mcp_result_v1"
CURRENT_READ_ATTESTATION_KEYS = {
    "connector_readiness": None,
    "list_sources": "catalog",
    "source_answer": "source_answer",
    "sources_answer": "sources_answer",
}


@dataclass
class AoACourseConnectorMCPState:
    connector_repo: Path
    owner_call: OwnerCall | None = None

    @classmethod
    def discover(cls) -> "AoACourseConnectorMCPState":
        raw = os.environ.get("AOA_COURSE_CONNECTOR_REPO")
        return cls(
            connector_repo=(
                Path(raw).expanduser().resolve()
                if raw
                else DEFAULT_CONNECTOR_REPO
            )
        )

    def source_route(self) -> dict[str, object]:
        return {
            "schema": "aoa_course_connector_mcp_source_route_v1",
            "service_name": SERVICE_NAME,
            "connector_repo": str(self.connector_repo),
            "connector_repo_exists": self.connector_repo.is_dir(),
            "source_owner": "aoa-course-connector",
            "access_owner": "abyss-stack",
            "owner_protocol": "2025-11-25",
            "published_owner_read_tools": sorted(OWNER_READ_TOOLS),
            "excluded_owner_effect_or_plan_tools": sorted(EXCLUDED_OWNER_TOOLS),
            "read_only": True,
            "network_touched": False,
            "stop_lines": [
                "Do not publish connected_run or any live/network execution route.",
                "Do not expose browser auth state, token values, cookies, or raw private course content.",
                "Do not turn fixture-safe execution into OS read authority.",
                "Do not duplicate course source, evidence, readiness, or answer meaning in abyss-stack.",
            ],
        }

    def status(self) -> dict[str, object]:
        return self._call("connector_readiness", {})

    def list_sources(
        self,
        source_ids: list[str] | None = None,
        include_disabled: bool = False,
    ) -> dict[str, object]:
        return self._call(
            "list_sources",
            {
                "source_ids": source_ids,
                "include_disabled": include_disabled,
                "include_source_refs": False,
                "include_connected_runs": True,
            },
        )

    def source_answer(
        self,
        query: str,
        source_id: str | None = None,
        limit: int = 5,
    ) -> dict[str, object]:
        return self._call(
            "source_answer",
            {
                "query": _query(query),
                "source_id": source_id,
                "include_source_refs": False,
                "limit": _limit(limit),
            },
        )

    def sources_answer(
        self,
        query: str,
        source_ids: list[str] | None = None,
        source_limit: int = 10,
        limit: int = 5,
    ) -> dict[str, object]:
        return self._call(
            "sources_answer",
            {
                "query": _query(query),
                "source_ids": source_ids,
                "include_source_refs": False,
                "source_limit": _limit(source_limit),
                "limit": _limit(limit),
            },
        )

    def lesson_context(
        self,
        query: str,
        run: str = "starter-fixture",
        limit: int = 5,
    ) -> dict[str, object]:
        return self._call(
            "lesson_context",
            {"query": _query(query), "run": run, "limit": _limit(limit)},
        )

    def graph_neighbors(
        self,
        node_id: str,
        run: str = "starter-fixture",
        limit: int = 20,
    ) -> dict[str, object]:
        if not str(node_id).strip():
            raise ValueError("node_id must not be empty")
        return self._call(
            "graph_neighbors",
            {"node_id": node_id, "run": run, "limit": _limit(limit)},
        )

    def freshness_report(
        self,
        run: str = "starter-fixture",
    ) -> dict[str, object]:
        return self._call("freshness_report", {"run": run})

    def evidence_report(
        self,
        query: str,
        run: str = "starter-fixture",
        limit: int = 5,
    ) -> dict[str, object]:
        return self._call(
            "evidence_report",
            {"query": _query(query), "run": run, "limit": _limit(limit)},
        )

    def _call(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        if tool_name not in OWNER_READ_TOOLS:
            raise PermissionError(f"owner tool is not in OS read allowlist: {tool_name}")
        cleaned = {key: value for key, value in arguments.items() if value is not None}
        result = (self.owner_call or self._owner_call())(tool_name, cleaned)
        if not isinstance(result, dict):
            raise TypeError("owner course MCP result must be an object")
        _require_owner_read_contract(tool_name, result)
        return {
            "schema": "aoa_course_connector_mcp_read_result_v1",
            "service_name": SERVICE_NAME,
            "owner_tool": tool_name,
            "owner_result": result,
            "read_only": True,
            "network_touched": False,
            "authority": "owner-result-preserved",
        }

    def _owner_call(self) -> OwnerCall:
        src = (self.connector_repo / "src").resolve()
        package = src / "aoa_course_connector"
        if not package.is_dir() or package.is_symlink():
            raise FileNotFoundError("owner course connector package is unavailable")
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        module = importlib.import_module("aoa_course_connector.mcp.server")
        config = importlib.import_module("aoa_course_connector.config")
        module_file = Path(module.__file__ or "").resolve()
        if not module_file.is_relative_to(src):
            raise RuntimeError("loaded course connector MCP API is not owner-rooted")
        roots = config.StorageRoots.from_env(self.connector_repo)

        def call(name: str, args: dict[str, object]) -> dict[str, object]:
            return module.call_tool(
                name,
                args,
                roots=roots,
                repo_root=self.connector_repo,
            )

        return call


def _query(value: str) -> str:
    query = str(value or "").strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        raise ValueError("query must be non-empty and bounded")
    return query


def _limit(value: int) -> int:
    limit = int(value)
    if limit < 1:
        raise ValueError("limit must be positive")
    return min(limit, MAX_LIMIT)


def _contains_true(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return value.get(key) is True or any(
            _contains_true(item, key) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_true(item, key) for item in value)
    return False


def _require_owner_read_contract(
    tool_name: str,
    result: dict[str, object],
) -> None:
    if result.get("tool") != tool_name:
        raise RuntimeError("owner result tool identity mismatch")

    attestation_key = CURRENT_READ_ATTESTATION_KEYS.get(tool_name)
    if tool_name == "connector_readiness":
        if result.get("schema") != "aoa_course_connector_readiness_v1":
            raise RuntimeError("owner readiness result schema mismatch")
        _require_current_read_attestation(result)
        return

    if result.get("schema") != OWNER_RESULT_SCHEMA:
        raise RuntimeError("owner result schema mismatch")
    if attestation_key is not None:
        attestation = result.get(attestation_key)
        if not isinstance(attestation, dict):
            raise RuntimeError(
                f"owner result missing {attestation_key} read attestation"
            )
        _require_current_read_attestation(attestation)
        return

    # These owner tools have no current-call attestation envelope. Their exact
    # source-reviewed allowlist remains authoritative, so retain the stricter
    # recursive denial until the owner publishes a direct invocation posture.
    if _contains_true(result, "network_touched"):
        raise PermissionError("owner result reported current network use")


def _require_current_read_attestation(
    attestation: dict[str, object],
) -> None:
    if attestation.get("network_touched") is not False:
        raise PermissionError("owner result did not prove network_touched=false")
    if attestation.get("read_only") is not True:
        raise PermissionError("owner result did not prove read_only=true")
