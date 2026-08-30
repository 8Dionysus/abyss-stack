"""Shared verification for declarative observe-only MCP canary contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


TARGETS_PATH = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "abyss-stack-mcp"
    / "src"
    / "abyss_stack_mcp"
    / "runtime-targets.v1.json"
)

_MISSING = object()


def load_canary_contracts(
    path: Path = TARGETS_PATH,
) -> dict[str, dict[str, Any]]:
    """Load reviewed read canaries without duplicating package identities."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unable to read MCP runtime target projection: {path}") from exc
    targets = payload.get("targets") if isinstance(payload, dict) else None
    if payload.get("schema_version") != "abyss_stack_runtime_targets_v1" or not isinstance(targets, list):
        raise RuntimeError("MCP runtime target projection has an unsupported shape")
    contracts: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict):
            raise RuntimeError("MCP runtime target projection contains a non-object")
        service_id = target.get("service_id")
        contract = target.get("canary_contract")
        effects = target.get("effect_classes")
        if not isinstance(service_id, str) or not isinstance(contract, dict):
            raise RuntimeError("MCP runtime target projection lacks a read canary contract")
        if effects != ["observe"]:
            raise RuntimeError(f"semantic fleet probe cannot invoke effectful target: {service_id}")
        if service_id in contracts:
            raise RuntimeError(f"MCP runtime target projection duplicates {service_id}")
        contracts[service_id] = contract
    return contracts


def _json_pointer(value: Any, pointer: str) -> Any:
    current = value
    if pointer == "":
        return current
    if not pointer.startswith("/"):
        return _MISSING
    for raw_segment in pointer.split("/")[1:]:
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING
            current = current[segment]
        elif isinstance(current, list) and segment.isdecimal():
            index = int(segment)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return current


def _nonempty(value: Any) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, (str, bytes, list, tuple, dict, set)):
        return bool(value)
    return True


def _contains_subset(value: Any, subset: dict[str, Any]) -> bool:
    return isinstance(value, list) and any(
        isinstance(item, dict)
        and all(item.get(key, _MISSING) == expected for key, expected in subset.items())
        for item in value
    )


def verify_structured_result(
    structured: Any,
    contract: Mapping[str, Any],
    *,
    transport: str | None = None,
) -> dict[str, Any]:
    """Return bounded contract facts; never include the owner payload itself."""

    reasons: list[str] = []
    if not isinstance(structured, dict):
        reasons.append("structured_content_missing")
    else:
        schema_pointer = contract.get("schema_pointer")
        schema_value = contract.get("schema_value")
        if not isinstance(schema_pointer, str) or _json_pointer(structured, schema_pointer) != schema_value:
            reasons.append("schema_identity_mismatch")
        for pointer in contract.get("required_pointers", []):
            if not isinstance(pointer, str) or not _nonempty(_json_pointer(structured, pointer)):
                reasons.append("required_evidence_missing")
                break
        exact_values = contract.get("exact_values", {})
        transport_exact_values = contract.get("transport_exact_values", {})
        if not isinstance(exact_values, Mapping):
            reasons.append("exact_values_invalid")
            exact_values = {}
        if not isinstance(transport_exact_values, Mapping):
            reasons.append("transport_exact_values_invalid")
            transport_exact_values = {}
        selected_transport_values = (
            transport_exact_values.get(transport, {})
            if transport is not None
            else {}
        )
        if not isinstance(selected_transport_values, Mapping):
            reasons.append("transport_exact_values_invalid")
            selected_transport_values = {}
        for pointer, expected in {
            **exact_values,
            **selected_transport_values,
        }.items():
            if _json_pointer(structured, pointer) != expected:
                reasons.append("exact_evidence_mismatch")
                break
        for assertion in contract.get("array_contains", []):
            if not isinstance(assertion, dict) or not _contains_subset(
                _json_pointer(structured, assertion.get("pointer", "")),
                assertion.get("subset", {}),
            ):
                reasons.append("array_evidence_missing")
                break
    reasons = list(dict.fromkeys(reasons))
    encoded = (
        json.dumps(structured, sort_keys=True, separators=(",", ":")).encode()
        if isinstance(structured, dict)
        else b""
    )
    schema_pointer = contract.get("schema_pointer")
    return {
        "structured_content": isinstance(structured, dict),
        "result_schema_identity": (
            _json_pointer(structured, schema_pointer)
            if isinstance(structured, dict) and isinstance(schema_pointer, str)
            else None
        ),
        "result_sha256": hashlib.sha256(encoded).hexdigest() if encoded else None,
        "reason_codes": reasons,
        "verdict": "passed" if not reasons else "failed",
    }
