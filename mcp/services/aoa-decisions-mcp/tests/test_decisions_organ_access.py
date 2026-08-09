from __future__ import annotations

import asyncio
import json
from pathlib import Path

import jsonschema
import pytest

from aoa_decisions_mcp.organ_access import CAPABILITY_ID
from aoa_decisions_mcp.organ_access import DecisionsOrganAccessError
from aoa_decisions_mcp.organ_access import load_organ_access_manifest
from aoa_decisions_mcp.organ_access import validate_organ_access_manifest
from aoa_decisions_mcp.server import CAPABILITY_PROFILE_ENV_VAR
from aoa_decisions_mcp.server import CAPABILITY_PROFILE_MAX_OUTPUT_BYTES
from aoa_decisions_mcp.server import _profile_packet
from aoa_decisions_mcp.server import build_server
from aoa_decisions_mcp.server import configured_capability_profile


SERVICE_ROOT = Path(__file__).resolve().parents[1]


def test_manifest_matches_schema_and_fail_closed_binding() -> None:
    manifest = load_organ_access_manifest()
    schema = json.loads(
        (SERVICE_ROOT / "organ-access.schema.json").read_text(encoding="utf-8")
    )

    jsonschema.Draft202012Validator(schema).validate(manifest)
    assert manifest["capabilities"][0]["capability_id"] == CAPABILITY_ID
    assert manifest["capabilities"][0]["credential_class"] == "decisions-read"
    assert all(value is False for value in manifest["guardrails"].values())


def test_manifest_rejects_authority_widening() -> None:
    manifest = load_organ_access_manifest()
    manifest["guardrails"]["decision_mutation_allowed"] = True

    with pytest.raises(DecisionsOrganAccessError, match="guardrails widened"):
        validate_organ_access_manifest(manifest)


def test_exact_profile_catalog_is_minimal_and_read_only() -> None:
    server = build_server(capability_profile=CAPABILITY_ID)

    async def inventory() -> tuple[set[str], set[str], set[str], set[str]]:
        tools = await server.list_tools()
        resources = await server.list_resources()
        templates = await server.list_resource_templates()
        prompts = await server.list_prompts()
        return (
            {tool.name for tool in tools},
            {str(resource.uri) for resource in resources},
            {template.uri_template for template in templates},
            {prompt.name for prompt in prompts},
        )

    tools, resources, templates, prompts = asyncio.run(inventory())
    assert tools == {
        "aoa_decisions_status",
        "aoa_decisions_packet",
        "aoa_decisions_decision",
    }
    assert resources == {"aoa-decisions://status"}
    assert templates == {"aoa-decisions://decision/{decision_id}"}
    assert prompts == set()
    for tool in asyncio.run(server.list_tools()):
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False


def test_profile_env_is_read_only_and_internal_effect_rejects_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CAPABILITY_PROFILE_ENV_VAR, CAPABILITY_ID)
    assert configured_capability_profile("read") == CAPABILITY_ID
    with pytest.raises(SystemExit, match="incompatible with internal_effect"):
        configured_capability_profile("internal_effect")
    with pytest.raises(SystemExit, match="incompatible"):
        build_server(contour="internal_effect", capability_profile=CAPABILITY_ID)


def test_profile_packet_is_compact_bounded_and_preserves_authority() -> None:
    payload = {
        "matches": [
            {
                "label": f"AAA-D-{index:04d}",
                "title": "x" * 2000,
                "status": "accepted",
                "path": f"docs/decisions/AAA-D-{index:04d}.md",
                "source_sha256": "a" * 64,
            }
            for index in range(20)
        ],
        "decision_views": [
            {
                "decision_id": f"AAA-D-{index:04d}",
                "repository_owner": "repo-a",
                "rationale_summary": "x" * 2000,
            }
            for index in range(20)
        ],
        "freshness": {
            "status": "fresh",
            "cache_status": "fresh",
            "remote_freshness_checked": False,
        },
        "authority_note": "repo-local source owns rationale",
        "claim_limits": ["bounded navigation only"],
    }

    result = _profile_packet(payload)

    assert result["truncated"] is True
    assert result["decision_count"] == len(result["decision_views"])
    assert result["authority_note"] == "repo-local source owns rationale"
    assert (
        len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode())
        <= CAPABILITY_PROFILE_MAX_OUTPUT_BYTES
    )
