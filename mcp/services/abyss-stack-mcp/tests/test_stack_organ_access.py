from __future__ import annotations

import json
import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from abyss_stack_mcp.organ_access import (
    CANDIDATE_CAPABILITY_ID,
    CANDIDATE_CREDENTIAL_CLASS,
    CANDIDATE_TOOL_BINDINGS,
    INTERNAL_EFFECT_CAPABILITY_ID,
    INTERNAL_EFFECT_CREDENTIAL_CLASS,
    INTERNAL_EFFECT_TOOL_BINDINGS,
    READ_CAPABILITY_ID,
    READ_CREDENTIAL_CLASS,
    READ_TOOL_BINDINGS,
    StackOrganAccessManifest,
    load_organ_access_manifest,
)
from abyss_stack_mcp.server import _build_policy_seam
from abyss_stack_mcp.effect_server import build_effect_server


SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict[str, object]:
    return json.loads(
        (SERVICE_ROOT / "organ-access.v1.json").read_text(encoding="utf-8")
    )


def test_owner_manifest_binds_exact_capabilities_and_runtime_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_organ_access_manifest(SERVICE_ROOT / "organ-access.v1.json")
    by_family = {item.policy_family: item for item in manifest.capabilities}

    assert by_family["read"].capability_id == READ_CAPABILITY_ID
    assert by_family["read"].credential_class == READ_CREDENTIAL_CLASS
    assert by_family["candidate"].capability_id == CANDIDATE_CAPABILITY_ID
    assert by_family["candidate"].credential_class == CANDIDATE_CREDENTIAL_CLASS
    assert by_family["internal_effect"].capability_id == INTERNAL_EFFECT_CAPABILITY_ID
    assert (
        by_family["internal_effect"].credential_class
        == INTERNAL_EFFECT_CREDENTIAL_CLASS
    )
    assert {
        item.primitive_id: item.mcp_name for item in by_family["read"].primitives
    } == READ_TOOL_BINDINGS
    assert {
        item.primitive_id: item.mcp_name
        for item in by_family["candidate"].primitives
    } == CANDIDATE_TOOL_BINDINGS
    assert {
        item.primitive_id: item.mcp_name
        for item in by_family["internal_effect"].primitives
    } == INTERNAL_EFFECT_TOOL_BINDINGS
    assert set(_build_policy_seam("read")._tools) == set(READ_TOOL_BINDINGS.values())
    assert set(_build_policy_seam("candidate")._tools) == set(
        CANDIDATE_TOOL_BINDINGS.values()
    )
    monkeypatch.setenv("AOA_MCP_TRANSPORT", "stdio")
    monkeypatch.delenv("ABYSS_STACK_MCP_REQUIRE_AUTH_MANIFEST", raising=False)
    assert {tool.name for tool in asyncio.run(build_effect_server().list_tools())} == set(
        INTERNAL_EFFECT_TOOL_BINDINGS.values()
    )
    assert manifest.contains_secrets is False
    assert manifest.admission_asserted is False
    assert manifest.registry_mutation_authorized is False
    assert manifest.effect_activation_authorized is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("shared_credential", "capability identity drifted"),
        ("read_tool", "capability identity drifted"),
        ("candidate_primitive", "capability identity drifted"),
        ("effect_primitive", "capability identity drifted"),
    ),
)
def test_owner_manifest_rejects_identity_drift(mutation: str, message: str) -> None:
    payload = _payload()
    capabilities = payload["capabilities"]
    assert isinstance(capabilities, list)
    read = capabilities[0]
    candidate = capabilities[1]
    internal_effect = capabilities[2]
    assert isinstance(read, dict)
    assert isinstance(candidate, dict)
    assert isinstance(internal_effect, dict)

    if mutation == "shared_credential":
        read["credential_class"] = CANDIDATE_CREDENTIAL_CLASS
    elif mutation == "read_tool":
        primitives = read["primitives"]
        assert isinstance(primitives, list)
        assert isinstance(primitives[0], dict)
        primitives[0]["mcp_name"] = "stack_runtime_catalog_drifted"
    elif mutation == "candidate_primitive":
        primitives = candidate["primitives"]
        assert isinstance(primitives, list)
        assert isinstance(primitives[0], dict)
        primitives[0]["primitive_id"] = "prepare-stack-plan"
    else:
        primitives = internal_effect["primitives"]
        assert isinstance(primitives, list)
        assert isinstance(primitives[0], dict)
        primitives[0]["mcp_name"] = "stack_execute_unbounded_effect"

    with pytest.raises(ValidationError, match=message):
        StackOrganAccessManifest.model_validate(payload)


def test_candidate_primitive_requires_rollback_route() -> None:
    payload = _payload()
    capabilities = payload["capabilities"]
    assert isinstance(capabilities, list)
    candidate = capabilities[1]
    assert isinstance(candidate, dict)
    primitives = candidate["primitives"]
    assert isinstance(primitives, list)
    primitive = primitives[0]
    assert isinstance(primitive, dict)
    primitive["rollback_route"] = None

    with pytest.raises(ValidationError, match="requires a rollback route"):
        StackOrganAccessManifest.model_validate(payload)


@pytest.mark.parametrize("field", ("approval_required", "rollback_route"))
def test_internal_effect_requires_approval_and_rollback(field: str) -> None:
    payload = _payload()
    capabilities = payload["capabilities"]
    assert isinstance(capabilities, list)
    internal_effect = capabilities[2]
    assert isinstance(internal_effect, dict)
    primitives = internal_effect["primitives"]
    assert isinstance(primitives, list)
    primitive = primitives[0]
    assert isinstance(primitive, dict)
    primitive[field] = False if field == "approval_required" else None

    with pytest.raises(ValidationError, match="internal-effect primitive requires"):
        StackOrganAccessManifest.model_validate(payload)
