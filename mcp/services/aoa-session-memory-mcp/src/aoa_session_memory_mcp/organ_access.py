"""Owner capability identity for bounded session-evidence access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CAPABILITY_ID = "session-evidence-read"
CREDENTIAL_CLASS = "session-memory-read"
TOOL_BINDINGS = {
    "plan-literal-route": "aoa_session_literal_query_plan",
    "search-session-evidence": "aoa_session_search",
    "retrieve-session-evidence": "aoa_session_retrieve",
    "assemble-evidence-packet": "aoa_session_evidence_packet",
    "check-evidence-freshness": "aoa_session_freshness_check",
    "inspect-entity-usage": "aoa_session_entity_usage_chain",
}
RESOURCE_TEMPLATE_BINDINGS = {
    "open-session-brief": "aoa-session-memory://session/{session}/brief",
    "open-session-manifest": "aoa-session-memory://session/{session}/manifest",
    "open-session-index": "aoa-session-memory://session/{session}/index",
    "open-session-rehydrate": "aoa-session-memory://session/{session}/rehydrate",
}
MANIFEST_PATH = Path(__file__).with_name("organ-access.v1.json")
SCHEMA_PATH = Path(__file__).with_name("organ-access.schema.json")


class SessionMemoryOrganAccessError(ValueError):
    """The owner capability manifest is unavailable or has drifted."""


def load_organ_access_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionMemoryOrganAccessError(
            "session-memory organ access manifest is unreadable"
        ) from exc
    _validate_manifest(payload)
    return payload


def load_organ_access_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    """Load the distributable JSON Schema without adding a runtime validator dependency."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionMemoryOrganAccessError(
            "session-memory organ access schema is unreadable"
        ) from exc
    if not isinstance(payload, dict) or payload.get("$id") != (
        "https://abyss.local/schemas/aoa-session-memory/organ-access-v1.json"
    ):
        raise SessionMemoryOrganAccessError(
            "session-memory organ access schema identity drifted"
        )
    return payload


def validate_runtime_bindings(
    payload: dict[str, Any],
    *,
    tool_names: set[str],
    resource_templates: set[str],
) -> None:
    """Require every admitted primitive to exist on the actual MCP surface."""

    _validate_manifest(payload)
    primitives = payload["capabilities"][0]["primitives"]
    declared_tools = {
        item["primitive_id"]: item["mcp_name"]
        for item in primitives
        if item["kind"] == "tool"
    }
    declared_templates = {
        item["primitive_id"]: item["mcp_name"]
        for item in primitives
        if item["kind"] == "resource_template"
    }
    if declared_tools != TOOL_BINDINGS:
        raise SessionMemoryOrganAccessError("session-memory tool bindings drifted")
    if declared_templates != RESOURCE_TEMPLATE_BINDINGS:
        raise SessionMemoryOrganAccessError(
            "session-memory resource-template bindings drifted"
        )
    if not set(declared_tools.values()).issubset(tool_names):
        raise SessionMemoryOrganAccessError(
            "an admitted session-memory tool is absent from the server"
        )
    if not set(declared_templates.values()).issubset(resource_templates):
        raise SessionMemoryOrganAccessError(
            "an admitted session-memory resource template is absent from the server"
        )


def _validate_manifest(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SessionMemoryOrganAccessError("organ access manifest must be an object")
    if payload.get("schema_version") != "aoa_session_memory_organ_access_v1":
        raise SessionMemoryOrganAccessError("unexpected organ access schema version")
    if payload.get("organ_id") != "aoa-session-memory":
        raise SessionMemoryOrganAccessError("unexpected organ access owner")
    if any(
        payload.get(field) is not False
        for field in (
            "contains_secrets",
            "admission_asserted",
            "registry_mutation_authorized",
            "effect_activation_authorized",
        )
    ):
        raise SessionMemoryOrganAccessError(
            "owner capability source cannot assert admission or effects"
        )
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) != 1:
        raise SessionMemoryOrganAccessError(
            "session-memory access requires one bounded capability"
        )
    capability = capabilities[0]
    if not isinstance(capability, dict):
        raise SessionMemoryOrganAccessError("session-memory capability must be an object")
    if (
        capability.get("capability_id") != CAPABILITY_ID
        or capability.get("policy_family") != "read"
        or capability.get("credential_class") != CREDENTIAL_CLASS
    ):
        raise SessionMemoryOrganAccessError("session-memory capability identity drifted")
    primitives = capability.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        raise SessionMemoryOrganAccessError("session-memory primitives are missing")
    identities: set[str] = set()
    names: set[str] = set()
    for primitive in primitives:
        if not isinstance(primitive, dict):
            raise SessionMemoryOrganAccessError("session-memory primitive must be an object")
        primitive_id = primitive.get("primitive_id")
        mcp_name = primitive.get("mcp_name")
        if not isinstance(primitive_id, str) or not primitive_id:
            raise SessionMemoryOrganAccessError("session-memory primitive id is invalid")
        if not isinstance(mcp_name, str) or not mcp_name:
            raise SessionMemoryOrganAccessError("session-memory MCP binding is invalid")
        if primitive_id in identities or mcp_name in names:
            raise SessionMemoryOrganAccessError("session-memory primitive bindings repeat")
        identities.add(primitive_id)
        names.add(mcp_name)
        if primitive.get("kind") not in {"tool", "resource_template"}:
            raise SessionMemoryOrganAccessError("unsupported session-memory MCP kind")
        if primitive.get("policy_family") != "read":
            raise SessionMemoryOrganAccessError("session-memory primitive left read policy")
        if primitive.get("effect_class") not in {"observe", "derive", "validate"}:
            raise SessionMemoryOrganAccessError("session-memory primitive effect is unsafe")
        if primitive.get("idempotency") != "read_only":
            raise SessionMemoryOrganAccessError("session-memory primitive is not read-only")
        if primitive.get("approval_required") is not False:
            raise SessionMemoryOrganAccessError("read primitive cannot require approval")
        if primitive.get("rollback_route") is not None:
            raise SessionMemoryOrganAccessError("read primitive cannot claim rollback")
        if primitive.get("annotations_are_security_enforcement") is not False:
            raise SessionMemoryOrganAccessError("MCP annotations cannot enforce security")
