#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SRC = SERVICE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_kag_mcp.core import AoAKagMCPState  # noqa: E402
from aoa_kag_mcp.server import build_server  # noqa: E402


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/aoa_kag_mcp/core.py",
        "src/aoa_kag_mcp/server.py",
        "scripts/aoa_kag_mcp_server.py",
    ]
    missing = [path for path in required if not (SERVICE_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AoAKagMCPState.discover()
    status = state.status()
    if not status["provider_map_exists"]:
        raise SystemExit("aoa-kag provider map is missing")
    if not status["readiness_exists"]:
        raise SystemExit("aoa-kag readiness matrix is missing")
    if not status["coverage_exists"]:
        raise SystemExit("aoa-kag repo-local coverage report is missing")
    if int(status["provider_count"]) < 1:
        raise SystemExit("aoa-kag provider map returned no providers")
    if state.provider_lookup("aoa-kag")["status"] != "provider_ready":
        raise SystemExit("aoa-kag provider lookup did not return provider_ready")
    provider_status = state.provider_status()
    source_index_repo = None
    for provider in provider_status["providers"]:
        repo_local_index = provider.get("repo_local_index")
        if not isinstance(repo_local_index, dict):
            continue
        if (
            repo_local_index.get("status") == "passed"
            and repo_local_index.get("source_index_ref")
        ):
            source_index_repo = str(provider["repo"])
            break
    if not source_index_repo:
        raise SystemExit("aoa-kag provider map returned no passed repo-local source index")
    repo_local_index = state.repo_local_index(source_index_repo)
    if repo_local_index["repo_local_index"].get("status") != "passed":
        raise SystemExit(f"{source_index_repo} repo-local index is not passed")
    source_index = state.source_index_status(source_index_repo)
    if not source_index["source_index_exists"]:
        raise SystemExit(f"{source_index_repo} source index resource is missing")
    common_surface_profile = state.common_surface_profile(source_index_repo)
    if common_surface_profile["common_surface_profile"].get("source") != "source_surface_index":
        raise SystemExit(f"{source_index_repo} common surface profile is not sourced from source_surface_index")
    if not state.freshness_check()["ok"]:
        raise SystemExit("aoa-kag provider freshness handles are missing receipts")
    generation = state.generation_route_lookup("aoa-kag")
    if generation["status"] != "available" or not generation["builder_routes"]:
        raise SystemExit("aoa-kag generation route lookup returned no builder routes")
    source_index = state.source_index_lookup("aoa-kag")
    if not source_index["repo_local_index"]:
        raise SystemExit("aoa-kag source-index lookup returned no repo-local index")
    coverage = state.repo_local_coverage_status()
    if int(coverage["count"]) < 1:
        raise SystemExit("aoa-kag repo-local coverage returned no owner rows")
    registry = state.registry_slice(limit=3)
    if not registry["items"]:
        raise SystemExit("aoa-kag registry slice returned no items")
    resource = state.read_resource("aoa-kag://registry/provider-map")
    if resource.get("schema_version") != "aoa-local-kag-provider-map-v1":
        raise SystemExit("aoa-kag provider-map resource has unexpected schema")
    profile_resource = state.read_resource(f"aoa-kag://providers/{source_index_repo}/common-surface-profile")
    if profile_resource["common_surface_profile"].get("source") != "source_surface_index":
        raise SystemExit(f"{source_index_repo} common-surface-profile resource is not readable")
    if state.read_resource("aoa-kag://providers/aoa-kag/generation")["status"] != "available":
        raise SystemExit("aoa-kag generation resource has unexpected status")
    if not state.read_resource(f"aoa-kag://providers/{source_index_repo}/source-index")["repo_local_index"]:
        raise SystemExit(f"{source_index_repo} source-index resource returned no index")
    if not state.read_resource(f"aoa-kag://providers/{source_index_repo}/repo-local-index")["repo_local_index"]:
        raise SystemExit(f"{source_index_repo} repo-local-index resource returned no index")
    if not state.read_resource("aoa-kag://coverage/repo-local-source-indexes")["owners"]:
        raise SystemExit("aoa-kag coverage resource returned no owners")
    server = build_server()
    if server is None:
        raise SystemExit("MCP server did not build")

    print(json.dumps({"ok": True, "provider_count": status["provider_count"]}, indent=2))


if __name__ == "__main__":
    main()
