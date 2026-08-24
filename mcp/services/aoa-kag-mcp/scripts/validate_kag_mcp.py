#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any


SERVICE_ROOT = Path(__file__).resolve().parents[1]
STACK_ROOT = SERVICE_ROOT.parents[2]
SRC = SERVICE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_kag_mcp.canonical import CanonicalRepoKag  # noqa: E402
from aoa_kag_mcp.core import AoAKagMCPState  # noqa: E402
from aoa_kag_mcp.server import build_server  # noqa: E402


EXPECTED_TOOLS = (
    "kag_discover",
    "kag_search",
    "kag_read",
    "kag_traverse",
    "kag_explain",
)
EXPECTED_RESOURCES = {
    "aoa-kag://capabilities",
    "aoa-kag://owners/{repo}/manifest",
    "aoa-kag://records/{qualified_id}",
    "aoa-kag://documents/{document_id}",
    "aoa-kag://anchors/{anchor_id}",
    "aoa-kag://sources/{repo}/{document_id}",
    "aoa-kag://evidence/{trace_id}",
    "aoa-kag://schemas/{name}",
    "aoa-kag://projections/{digest}",
}
EXPECTED_SCHEMAS = {
    "kag-mcp-capabilities.schema.json": "aoa-kag-mcp-capabilities-v1",
    "kag-mcp-result.schema.json": "aoa-kag-mcp-result-v1",
}
EXPECTED_RUNTIME_ROUTE = "abyss-stack/mechanics/federation-seams/parts/kag-seam"


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


def _field(value: Any, *names: str) -> Any:
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _validate_owner_contract(state: AoAKagMCPState) -> int:
    for label, exists in (
        ("provider map", state.provider_map_exists()),
        ("readiness matrix", state.readiness_exists()),
        ("repo-local coverage", state.coverage_exists()),
    ):
        if not exists:
            raise SystemExit(f"aoa-kag {label} is missing")

    provider_map = state.provider_map()
    providers = provider_map.get("providers")
    if not isinstance(providers, list) or not providers:
        raise SystemExit("aoa-kag provider map returned no providers")
    handoff = provider_map.get("mcp_handoff")
    if not isinstance(handoff, dict):
        raise SystemExit("aoa-kag provider map has no MCP handoff")
    if handoff.get("tools") != list(EXPECTED_TOOLS):
        raise SystemExit("aoa-kag MCP handoff tool contract drifted")
    templates = handoff.get("resource_templates")
    if not isinstance(templates, list):
        raise SystemExit("aoa-kag MCP handoff resources are missing")
    resource_uris = {
        str(item.get("uri_template"))
        for item in templates
        if isinstance(item, dict) and item.get("uri_template")
    }
    if resource_uris != EXPECTED_RESOURCES:
        raise SystemExit("aoa-kag MCP handoff resource contract drifted")
    if handoff.get("prompts") != []:
        raise SystemExit("aoa-kag MCP handoff prompt contract drifted")
    if handoff.get("runtime_state_route") != EXPECTED_RUNTIME_ROUTE:
        raise SystemExit("aoa-kag MCP runtime owner route drifted")

    for filename, schema_version in EXPECTED_SCHEMAS.items():
        schema = _read_object(state.aoa_kag_root / "schemas" / filename)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"{filename} must use JSON Schema 2020-12")
        properties = schema.get("properties")
        version_property = (
            properties.get("schema_version") if isinstance(properties, dict) else None
        )
        if not isinstance(version_property, dict) or version_property.get("const") != schema_version:
            raise SystemExit(f"{filename} carries an unexpected schema version")
    return len(providers)


def _validate_server_contract(state: AoAKagMCPState) -> tuple[int, int]:
    server = build_server(
        workspace_root=state.workspace_root,
        aoa_kag_root=state.aoa_kag_root,
        provider_map_path=state.provider_map_path,
        readiness_path=state.readiness_path,
        coverage_path=state.coverage_path,
        stack_root=STACK_ROOT,
    )
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    if set(tools) != set(EXPECTED_TOOLS):
        raise SystemExit("aoa-kag MCP server tool surface drifted")
    for tool in tools.values():
        annotations = tool.annotations
        if (
            not _field(tool, "output_schema", "outputSchema")
            or annotations is None
            or _field(annotations, "read_only_hint", "readOnlyHint") is not True
            or _field(annotations, "destructive_hint", "destructiveHint") is not False
            or _field(annotations, "idempotent_hint", "idempotentHint") is not True
            or _field(annotations, "open_world_hint", "openWorldHint") is not False
        ):
            raise SystemExit(f"{tool.name} must keep its read-only structured contract")

    search_limit = _field(tools["kag_search"], "input_schema", "inputSchema")[
        "properties"
    ]["limit"]
    traversal_depth = _field(tools["kag_traverse"], "input_schema", "inputSchema")[
        "properties"
    ]["max_depth"]
    traversal_limit = _field(tools["kag_traverse"], "input_schema", "inputSchema")[
        "properties"
    ]["limit"]
    if (search_limit.get("minimum"), search_limit.get("maximum")) != (1, 10):
        raise SystemExit("kag_search limit contract drifted")
    if (traversal_limit.get("minimum"), traversal_limit.get("maximum")) != (1, 10):
        raise SystemExit("kag_traverse limit contract drifted")
    if (traversal_depth.get("minimum"), traversal_depth.get("maximum")) != (1, 4):
        raise SystemExit("kag_traverse depth contract drifted")

    resources = {str(item.uri) for item in asyncio.run(server.list_resources())}
    resources.update(
        str(_field(item, "uri_template", "uriTemplate"))
        for item in asyncio.run(server.list_resource_templates())
    )
    if resources != EXPECTED_RESOURCES:
        raise SystemExit("aoa-kag MCP server resource surface drifted")
    if asyncio.run(server.list_prompts()):
        raise SystemExit("aoa-kag MCP server unexpectedly exposes prompts")
    return len(tools), len(resources)


def _validate_portable_canonical_read(state: AoAKagMCPState) -> str:
    providers = sorted(
        state.providers(),
        key=lambda provider: provider.get("repo") != "aoa-kag",
    )
    canonical = CanonicalRepoKag(state)
    for provider in providers:
        repo = str(provider.get("repo") or "")
        packet = provider.get("repo_local_index")
        if (
            not repo
            or not isinstance(packet, dict)
            or packet.get("family_storage") != "v3-portable-shards"
        ):
            continue
        family_path = state.canonical_family_path(repo)
        if family_path is None or not family_path.is_file():
            continue
        discovery = canonical.discover_owner(repo)
        digest = canonical.owner_digest(repo)
        if not isinstance(discovery, dict) or not digest:
            raise SystemExit(
                f"aoa-kag MCP canonical portable read failed for {repo}"
            )
        return repo
    raise SystemExit("aoa-kag MCP found no readable portable KAG provider")


def main() -> None:
    required = (
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/aoa_kag_mcp/canonical.py",
        "src/aoa_kag_mcp/cli.py",
        "src/aoa_kag_mcp/core.py",
        "src/aoa_kag_mcp/runtime.py",
        "src/aoa_kag_mcp/server.py",
        "scripts/aoa_kag_mcp_server.py",
    )
    missing = [path for path in required if not (SERVICE_ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AoAKagMCPState.discover()
    provider_count = _validate_owner_contract(state)
    tool_count, resource_count = _validate_server_contract(state)
    canonical_owner = _validate_portable_canonical_read(state)
    print(
        json.dumps(
            {
                "ok": True,
                "provider_count": provider_count,
                "tool_count": tool_count,
                "resource_count": resource_count,
                "prompt_count": 0,
                "canonical_portable_owner": canonical_owner,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
