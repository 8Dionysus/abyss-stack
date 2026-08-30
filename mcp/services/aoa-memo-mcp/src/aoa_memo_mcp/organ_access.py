"""Runtime binding for the owner-authored aoa-memo organ capabilities."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ._runtime_config import PATH_CONFIG


READ_CAPABILITY_ID = "durable-memory-read"
CANDIDATE_CAPABILITY_ID = "memory-candidate-prepare"
READ_CREDENTIAL_CLASS = "memo-read"
CANDIDATE_CREDENTIAL_CLASS = "memo-candidate"
ORGAN_ACCESS_MANIFEST_ENV_VAR = "AOA_MEMO_MCP_ORGAN_ACCESS_MANIFEST"
OWNER_MANIFEST_RELATIVE_PATH = Path(
    "mechanics/consumer-handoff/parts/mcp-organ-access/config/organ-access.v1.json"
)
READ_TOOL_BINDINGS = {
    "brief-reviewed-memory": "aoa_memo_recall_brief",
    "recall-reviewed-memory": "aoa_memo_recall_reviewed",
    "read-reviewed-object": "aoa_memo_read_object",
}
READ_RESOURCE_TEMPLATE_BINDINGS = {
    "open-reviewed-object": "aoa-memo://memory/object/{object_id}",
}
CANDIDATE_TOOL_BINDINGS = {
    "create-local-candidate": "aoa_memo_create_candidate",
    "prepare-intake-packet": "aoa_memo_prepare_intake_packet",
    "prepare-forwarding-receipt": "aoa_memo_prepare_forwarding_receipt",
}


class MemoOrganAccessError(ValueError):
    """The owner capability source is missing or does not bind this runtime."""


def owner_manifest_path(workspace_root: str | Path | None = None) -> Path:
    explicit = os.environ.get(ORGAN_ACCESS_MANIFEST_ENV_VAR, "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    root = PATH_CONFIG.workspace_root(workspace_root)
    return root / "aoa-memo" / OWNER_MANIFEST_RELATIVE_PATH


def load_owner_manifest(workspace_root: str | Path | None = None) -> dict[str, Any]:
    path = owner_manifest_path(workspace_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MemoOrganAccessError(
            f"aoa-memo organ access manifest is unreadable: {path}"
        ) from exc
    _validate_owner_manifest(payload)
    return payload


def capability(payload: dict[str, Any], capability_id: str) -> dict[str, Any]:
    for item in payload["capabilities"]:
        if item.get("capability_id") == capability_id:
            return item
    raise MemoOrganAccessError(f"aoa-memo capability is missing: {capability_id}")


def validate_runtime_bindings(
    payload: dict[str, Any],
    *,
    capability_id: str,
    tool_names: set[str],
    resource_templates: set[str],
) -> None:
    _validate_owner_manifest(payload)
    selected = capability(payload, capability_id)
    declared_tools = {
        item["primitive_id"]: item["mcp_name"]
        for item in selected["primitives"]
        if item["kind"] == "tool"
    }
    declared_templates = {
        item["primitive_id"]: item["mcp_name"]
        for item in selected["primitives"]
        if item["kind"] == "resource_template"
    }
    expected_tools = (
        READ_TOOL_BINDINGS
        if capability_id == READ_CAPABILITY_ID
        else CANDIDATE_TOOL_BINDINGS
    )
    expected_templates = (
        READ_RESOURCE_TEMPLATE_BINDINGS
        if capability_id == READ_CAPABILITY_ID
        else {}
    )
    if declared_tools != expected_tools or declared_templates != expected_templates:
        raise MemoOrganAccessError("aoa-memo owner/runtime primitive bindings drifted")
    if set(declared_tools.values()) != tool_names:
        raise MemoOrganAccessError("aoa-memo runtime tool catalog drifted")
    if set(declared_templates.values()) != resource_templates:
        raise MemoOrganAccessError("aoa-memo runtime resource catalog drifted")


def _validate_owner_manifest(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise MemoOrganAccessError("aoa-memo organ access manifest must be an object")
    expected_identity = {
        "schema_version": "aoa_memo_organ_access_v1",
        "organ_id": "aoa-memo",
        "source_owner": "aoa-memo",
        "access_runtime_owner": "abyss-stack",
        "admission_owner": "aoa-sdk",
        "proof_owner": "aoa-evals",
    }
    if any(payload.get(key) != value for key, value in expected_identity.items()):
        raise MemoOrganAccessError("aoa-memo organ access identity drifted")
    for key in (
        "contains_secrets",
        "admission_asserted",
        "owner_acceptance_asserted",
        "proof_asserted",
        "effect_activation_authorized",
    ):
        if payload.get(key) is not False:
            raise MemoOrganAccessError(f"aoa-memo owner source cannot assert {key}")
    guardrails = payload.get("guardrails")
    if not isinstance(guardrails, dict) or any(value is not False for value in guardrails.values()):
        raise MemoOrganAccessError("aoa-memo organ access guardrails widened")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) != 2:
        raise MemoOrganAccessError("aoa-memo requires two exact capability contours")
    identities = {item.get("capability_id") for item in capabilities if isinstance(item, dict)}
    if identities != {READ_CAPABILITY_ID, CANDIDATE_CAPABILITY_ID}:
        raise MemoOrganAccessError("aoa-memo capability identities drifted")
    read = capability(payload, READ_CAPABILITY_ID)
    candidate = capability(payload, CANDIDATE_CAPABILITY_ID)
    if (
        read.get("policy_family") != "read"
        or read.get("process_contour") != "read"
        or read.get("credential_class") != READ_CREDENTIAL_CLASS
        or candidate.get("policy_family") != "candidate"
        or candidate.get("process_contour") != "candidate"
        or candidate.get("credential_class") != CANDIDATE_CREDENTIAL_CLASS
    ):
        raise MemoOrganAccessError("aoa-memo capability contour or credential drifted")
    names: set[str] = set()
    for selected in capabilities:
        primitives = selected.get("primitives")
        if not isinstance(primitives, list) or not primitives:
            raise MemoOrganAccessError("aoa-memo capability primitives are missing")
        for primitive in primitives:
            if not isinstance(primitive, dict):
                raise MemoOrganAccessError("aoa-memo primitive must be an object")
            name = primitive.get("mcp_name")
            if not isinstance(name, str) or not name or name in names:
                raise MemoOrganAccessError("aoa-memo primitive name is invalid or repeated")
            names.add(name)
            if primitive.get("approval_required") is not False:
                raise MemoOrganAccessError("aoa-memo primitive cannot infer approval")
