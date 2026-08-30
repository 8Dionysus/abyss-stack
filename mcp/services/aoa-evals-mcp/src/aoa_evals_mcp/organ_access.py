"""Runtime binding for the owner-authored aoa-evals organ capabilities."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ._runtime_config import PATH_CONFIG


DISCOVERY_CAPABILITY_ID = "eval-discovery-read"
REQUEST_CAPABILITY_ID = "eval-request-prepare"
PROOF_RESULT_CAPABILITY_ID = "proof-result-read"
READ_CREDENTIAL_CLASS = "evals-read"
CANDIDATE_CREDENTIAL_CLASS = "evals-candidate"
ORGAN_ACCESS_MANIFEST_ENV_VAR = "AOA_EVALS_MCP_ORGAN_ACCESS_MANIFEST"
OWNER_MANIFEST_RELATIVE_PATH = Path(
    "docs/architecture/aoa_evals_mcp_capabilities.v1.json"
)

TOOL_BINDINGS = {
    DISCOVERY_CAPABILITY_ID: {
        "select-bounded-eval": "aoa_evals_select",
        "inspect-bounded-eval": "aoa_evals_inspect",
        "read-eval-sections": "aoa_evals_expand",
        "read-evals-freshness": "aoa_evals_runtime_status",
    },
    REQUEST_CAPABILITY_ID: {
        "prepare-eval-request": "aoa_evals_prepare_request_candidate",
    },
    PROOF_RESULT_CAPABILITY_ID: {
        "read-issued-proof-result": "aoa_evals_read_proof_result",
    },
}
RESOURCE_TEMPLATE_BINDINGS = {
    DISCOVERY_CAPABILITY_ID: {
        "open-eval-catalog": "aoa-evals://catalog",
        "open-eval-bundle": "aoa-evals://bundle/{name}",
        "open-eval-sections": "aoa-evals://bundle/{name}/sections",
        "open-evals-freshness": "aoa-evals://runtime-status",
    },
    REQUEST_CAPABILITY_ID: {},
    PROOF_RESULT_CAPABILITY_ID: {
        "open-issued-proof-result": "aoa-evals://proof-result/{report_id}",
    },
}


class EvalsOrganAccessError(ValueError):
    """The owner capability source is missing or does not bind this runtime."""


def owner_manifest_path(
    workspace_root: str | Path | None = None,
    evals_root: str | Path | None = None,
) -> Path:
    explicit = os.environ.get(ORGAN_ACCESS_MANIFEST_ENV_VAR, "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if evals_root is not None:
        return Path(evals_root).expanduser().resolve() / OWNER_MANIFEST_RELATIVE_PATH
    root = PATH_CONFIG.workspace_root(workspace_root)
    return root / "aoa-evals" / OWNER_MANIFEST_RELATIVE_PATH


def load_owner_manifest(
    workspace_root: str | Path | None = None,
    evals_root: str | Path | None = None,
) -> dict[str, Any]:
    path = owner_manifest_path(workspace_root, evals_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalsOrganAccessError(
            f"aoa-evals organ access manifest is unreadable: {path}"
        ) from exc
    _validate_owner_manifest(payload)
    return payload


def capability(payload: dict[str, Any], capability_id: str) -> dict[str, Any]:
    for item in payload["capabilities"]:
        if item.get("capability_id") == capability_id:
            return item
    raise EvalsOrganAccessError(f"aoa-evals capability is missing: {capability_id}")


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
        if item["kind"] in {"resource", "resource_template"}
    }
    if declared_tools != TOOL_BINDINGS[capability_id]:
        raise EvalsOrganAccessError("aoa-evals owner/runtime tool bindings drifted")
    if declared_templates != RESOURCE_TEMPLATE_BINDINGS[capability_id]:
        raise EvalsOrganAccessError(
            "aoa-evals owner/runtime resource bindings drifted"
        )
    if set(declared_tools.values()) != tool_names:
        raise EvalsOrganAccessError("aoa-evals runtime tool catalog drifted")
    if set(declared_templates.values()) != resource_templates:
        raise EvalsOrganAccessError("aoa-evals runtime resource catalog drifted")


def _validate_owner_manifest(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise EvalsOrganAccessError("aoa-evals organ access manifest must be an object")
    expected_identity = {
        "schema_version": "aoa_evals_mcp_capabilities_v1",
        "organ_id": "aoa-evals",
        "source_owner": "aoa-evals",
        "access_runtime_owner": "abyss-stack",
        "admission_owner": "aoa-sdk",
        "proof_owner": "aoa-evals",
    }
    if any(payload.get(key) != value for key, value in expected_identity.items()):
        raise EvalsOrganAccessError("aoa-evals organ access identity drifted")
    for key in (
        "contains_secrets",
        "admission_asserted",
        "owner_acceptance_asserted",
        "proof_issuance_via_mcp_allowed",
        "effect_activation_authorized",
    ):
        if payload.get(key) is not False:
            raise EvalsOrganAccessError(f"aoa-evals owner source cannot assert {key}")
    guardrails = payload.get("guardrails")
    if not isinstance(guardrails, dict) or any(
        value is not False for value in guardrails.values()
    ):
        raise EvalsOrganAccessError("aoa-evals organ access guardrails widened")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) != 3:
        raise EvalsOrganAccessError("aoa-evals requires three exact capabilities")
    identities = {
        item.get("capability_id")
        for item in capabilities
        if isinstance(item, dict)
    }
    expected_capabilities = {
        DISCOVERY_CAPABILITY_ID,
        REQUEST_CAPABILITY_ID,
        PROOF_RESULT_CAPABILITY_ID,
    }
    if identities != expected_capabilities:
        raise EvalsOrganAccessError("aoa-evals capability identities drifted")

    expected_contours = {
        DISCOVERY_CAPABILITY_ID: ("read", "read", READ_CREDENTIAL_CLASS),
        REQUEST_CAPABILITY_ID: (
            "candidate",
            "candidate",
            CANDIDATE_CREDENTIAL_CLASS,
        ),
        PROOF_RESULT_CAPABILITY_ID: ("read", "read", READ_CREDENTIAL_CLASS),
    }
    names: set[str] = set()
    for selected in capabilities:
        capability_id = selected["capability_id"]
        observed = (
            selected.get("policy_family"),
            selected.get("process_contour"),
            selected.get("credential_class"),
        )
        if observed != expected_contours[capability_id]:
            raise EvalsOrganAccessError(
                "aoa-evals capability contour or credential drifted"
            )
        primitives = selected.get("primitives")
        if not isinstance(primitives, list) or not primitives:
            raise EvalsOrganAccessError("aoa-evals capability primitives are missing")
        for primitive in primitives:
            if not isinstance(primitive, dict):
                raise EvalsOrganAccessError("aoa-evals primitive must be an object")
            name = primitive.get("mcp_name")
            if not isinstance(name, str) or not name or name in names:
                raise EvalsOrganAccessError(
                    "aoa-evals primitive name is invalid or repeated"
                )
            names.add(name)
            if primitive.get("approval_required") is not False:
                raise EvalsOrganAccessError("aoa-evals primitive cannot infer approval")
