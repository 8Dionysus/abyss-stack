"""Fail-closed binding for the stack-owned Decisions access capability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CAPABILITY_ID = "decision-retrieval"
CREDENTIAL_CLASS = "decisions-read"
MANIFEST_PATH = Path(__file__).resolve().parents[2] / "organ-access.v1.json"
TOOL_BINDINGS = {
    "read-decision-cache-posture": "aoa_decisions_status",
    "find-owner-decisions": "aoa_decisions_packet",
    "read-owner-decision-neighborhood": "aoa_decisions_decision",
}
RESOURCE_BINDINGS = {
    "open-decision-cache-posture": "aoa-decisions://status",
    "open-owner-decision-neighborhood": "aoa-decisions://decision/{decision_id}",
}


class DecisionsOrganAccessError(ValueError):
    """The Decisions capability source is missing or drifted."""


def load_organ_access_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionsOrganAccessError(
            f"aoa-decisions organ access manifest is unreadable: {path}"
        ) from exc
    validate_organ_access_manifest(payload)
    return payload


def validate_organ_access_manifest(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise DecisionsOrganAccessError("aoa-decisions manifest must be an object")
    expected_identity = {
        "schema_version": "aoa_decisions_mcp_organ_access_v1",
        "organ_id": "aoa-decisions",
        "source_owner": "federated-repository-decision-owners",
        "access_runtime_owner": "abyss-stack",
        "admission_owner": "aoa-sdk",
        "proof_owner": "aoa-evals",
    }
    if any(payload.get(key) != value for key, value in expected_identity.items()):
        raise DecisionsOrganAccessError("aoa-decisions owner identity drifted")
    for key in (
        "contains_secrets",
        "admission_asserted",
        "owner_acceptance_asserted",
        "effect_activation_authorized",
    ):
        if payload.get(key) is not False:
            raise DecisionsOrganAccessError(f"aoa-decisions cannot assert {key}")
    guardrails = payload.get("guardrails")
    if not isinstance(guardrails, dict) or not guardrails or any(
        value is not False for value in guardrails.values()
    ):
        raise DecisionsOrganAccessError("aoa-decisions guardrails widened")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) != 1:
        raise DecisionsOrganAccessError("aoa-decisions requires one exact capability")
    capability = capabilities[0]
    if not isinstance(capability, dict):
        raise DecisionsOrganAccessError("aoa-decisions capability must be an object")
    contour = (
        capability.get("capability_id"),
        capability.get("policy_family"),
        capability.get("process_contour"),
        capability.get("credential_class"),
    )
    if contour != (CAPABILITY_ID, "read", "read", CREDENTIAL_CLASS):
        raise DecisionsOrganAccessError("aoa-decisions capability contour drifted")
    primitives = capability.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        raise DecisionsOrganAccessError("aoa-decisions primitives are missing")
    tools = {
        item.get("primitive_id"): item.get("mcp_name")
        for item in primitives
        if isinstance(item, dict) and item.get("kind") == "tool"
    }
    resources = {
        item.get("primitive_id"): item.get("mcp_name")
        for item in primitives
        if isinstance(item, dict)
        and item.get("kind") in {"resource", "resource_template"}
    }
    if tools != TOOL_BINDINGS or resources != RESOURCE_BINDINGS:
        raise DecisionsOrganAccessError("aoa-decisions primitive bindings drifted")
    if any(
        not isinstance(item, dict)
        or item.get("effect_class") != "observe"
        or item.get("approval_required") is not False
        for item in primitives
    ):
        raise DecisionsOrganAccessError("aoa-decisions primitive authority widened")


def validate_runtime_bindings(
    payload: dict[str, Any],
    *,
    tool_names: set[str],
    resource_names: set[str],
) -> None:
    validate_organ_access_manifest(payload)
    if tool_names != set(TOOL_BINDINGS.values()):
        raise DecisionsOrganAccessError("aoa-decisions runtime tool catalog drifted")
    if resource_names != set(RESOURCE_BINDINGS.values()):
        raise DecisionsOrganAccessError("aoa-decisions runtime resource catalog drifted")
