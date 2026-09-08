from __future__ import annotations

import copy
import json
import os

import pytest
from jsonschema import Draft202012Validator

from aoa_session_memory_mcp.organ_access import (
    CAPABILITY_ID,
    CREDENTIAL_CLASS,
    RESOURCE_TEMPLATE_BINDINGS,
    TOOL_BINDINGS,
    SessionMemoryOrganAccessError,
    load_organ_access_manifest,
    load_organ_access_schema,
    validate_runtime_bindings,
)
from aoa_session_memory_mcp.server import build_server
from aoa_session_memory_mcp.server import CAPABILITY_PROFILE_ENV_VAR
from aoa_session_memory_mcp.server import CAPABILITY_PROFILE_MAX_OUTPUT_BYTES
from aoa_session_memory_mcp.server import _default_http_capability_profile
from aoa_session_memory_mcp.server import _payload_bytes
from aoa_session_memory_mcp.server import _project_capability_output
from aoa_session_memory_mcp.server import _project_capability_retrieve_candidates


def _surface() -> tuple[set[str], set[str]]:
    server = build_server()
    tools = set(server._tool_manager._tools)
    templates = {
        str(item.uri_template)
        for item in server._resource_manager._templates.values()
    }
    return tools, templates


def test_owner_capability_binds_bounded_tools_and_resource_templates() -> None:
    payload = load_organ_access_manifest()
    Draft202012Validator(load_organ_access_schema()).validate(payload)
    tools, templates = _surface()

    validate_runtime_bindings(
        payload,
        tool_names=tools,
        resource_templates=templates,
    )
    capability = payload["capabilities"][0]
    assert capability["capability_id"] == CAPABILITY_ID
    assert capability["credential_class"] == CREDENTIAL_CLASS
    assert len(TOOL_BINDINGS) == 6
    assert len(RESOURCE_TEMPLATE_BINDINGS) == 4
    assert payload["access_strategy"]["bulk_index_loading_allowed"] is False
    assert payload["access_strategy"]["raw_transcript_default_allowed"] is False
    assert payload["admission_asserted"] is False
    assert payload["registry_mutation_authorized"] is False
    assert payload["effect_activation_authorized"] is False


def test_owner_capability_rejects_tool_identity_drift() -> None:
    payload = copy.deepcopy(load_organ_access_manifest())
    payload["capabilities"][0]["primitives"][0]["mcp_name"] = (
        "aoa_session_literal_query_plan_drifted"
    )
    tools, templates = _surface()

    with pytest.raises(SessionMemoryOrganAccessError, match="tool bindings drifted"):
        validate_runtime_bindings(
            payload,
            tool_names=tools,
            resource_templates=templates,
        )


def test_owner_capability_rejects_authority_inference() -> None:
    payload = copy.deepcopy(load_organ_access_manifest())
    payload["admission_asserted"] = True

    with pytest.raises(SessionMemoryOrganAccessError, match="cannot assert"):
        validate_runtime_bindings(
            payload,
            tool_names=set(TOOL_BINDINGS.values()),
            resource_templates=set(RESOURCE_TEMPLATE_BINDINGS.values()),
        )


def test_owner_capability_profile_removes_unadmitted_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CAPABILITY_PROFILE_ENV_VAR, CAPABILITY_ID)
    server = build_server()

    assert set(server._tool_manager._tools) == set(TOOL_BINDINGS.values())
    assert server._resource_manager._resources == {}
    assert {
        str(item.uri_template)
        for item in server._resource_manager._templates.values()
    } == set(RESOURCE_TEMPLATE_BINDINGS.values())
    assert server._prompt_manager._prompts == {}


def test_unknown_capability_profile_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CAPABILITY_PROFILE_ENV_VAR, "unknown-profile")

    with pytest.raises(SystemExit, match="must be 'session-evidence-read'"):
        build_server()


def test_default_profile_narrows_http_but_not_portable_stdio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(CAPABILITY_PROFILE_ENV_VAR, raising=False)
    monkeypatch.setenv("AOA_MCP_TRANSPORT", "stdio")
    assert _default_http_capability_profile() is None
    assert CAPABILITY_PROFILE_ENV_VAR not in os.environ

    monkeypatch.setenv("AOA_MCP_TRANSPORT", "streamable-http")
    assert _default_http_capability_profile() == CAPABILITY_ID
    assert CAPABILITY_PROFILE_ENV_VAR not in os.environ


def test_capability_projection_removes_bulky_provider_metadata() -> None:
    payload = {
        "ok": True,
        "provider": {
            "selected": "portable_sqlite",
            "status": {
                "ok": False,
                "selected_provider": "portable_sqlite",
                "providers": {
                    "portable_sqlite": {
                        "ok": False,
                        "status": "stale",
                        "metadata": {"large": "x" * 40_000},
                        "diagnostics": ["projection_dirty"],
                    }
                },
            },
            "authority_law": "raw refs remain authority",
        },
        "evidence_hits": [{"raw_ref": "raw:line:1", "preview": "bounded"}],
    }

    projected = _project_capability_output("aoa_session_retrieve", payload)

    assert projected["ok"] is True
    assert "metadata" not in str(projected["provider"])
    assert projected["mcp_access"]["source_payload_bytes"] > 40_000
    assert _payload_bytes(projected) <= CAPABILITY_PROFILE_MAX_OUTPUT_BYTES


def test_capability_projection_compacts_nested_evidence_packet_and_preserves_refs() -> None:
    provider = {
        "selected": "portable_sqlite",
        "authoritative_result_provider": "portable_sqlite",
        "status": {
            "ok": False,
            "selected_provider": "portable_sqlite",
            "reasons": ["portable provider is stale"],
            "providers": {
                "portable_sqlite": {
                    "ok": False,
                    "status": "stale",
                    "reasons": ["freshness state is dirty"],
                    "metadata": {"large": "x" * 40_000},
                    "freshness": {
                        "status": "stale",
                        "reasons": ["freshness state is dirty"],
                        "diagnostics": ["projection_dirty"],
                        "dirty_session_ids": ["session-1", "session-2"],
                    },
                    "diagnostics": ["projection_dirty"],
                }
            },
        },
    }
    freshness_provider = {
        "schema_version": 1,
        "artifact_type": "search_provider_status",
        "ok": False,
        "selected_provider": "portable_sqlite",
        "reasons": ["portable provider is stale"],
        "diagnostics": ["portable_sqlite:stale"],
        "providers": {
            "portable_sqlite": {
                "provider": "portable_sqlite",
                "ok": False,
                "status": "stale",
                "reasons": ["freshness state is dirty"],
                "metadata": {"large": "x" * 40_000},
                "diagnostics": ["projection_dirty"],
                "freshness": {
                    "status": "stale",
                    "dirty_session_ids": [f"session-{index}" for index in range(100)],
                    "dirty_session_count": 100,
                },
            }
        },
    }
    evidence_item = {
        "event_id": "event-1",
        "raw_ref": "raw:line:17",
        "segment_ref": "segment-1.md#event-1",
        "session_ref": "session:session-1",
        "refs": {
            "raw": "raw:line:17",
            "segment": "segment-1.md#event-1",
            "session": "session:session-1",
        },
        "preview": "bounded evidence",
        "body": "x" * 40_000,
    }
    payload = {
        "schema": "aoa_session_memory_evidence_packet_v1",
        "ok": True,
        "mutates": False,
        "candidate_posture": "candidate evidence for review; not a verdict",
        "search_hits": [evidence_item],
        "retrieval_packet": {
            "ok": True,
            "provider": provider,
            "evidence_hits": [evidence_item],
        },
        "route_traces": [
            {
                "ok": True,
                "provider": provider,
                "results": [evidence_item],
            }
        ],
        "freshness": {
            "ok": False,
            "provider": freshness_provider,
            "checks": [{"ref": "raw:line:17", "status": "present"}],
            "diagnostics": ["provider stale"],
        },
    }

    projected = _project_capability_output("aoa_session_evidence_packet", payload)

    assert projected["ok"] is True
    assert _payload_bytes(projected) <= CAPABILITY_PROFILE_MAX_OUTPUT_BYTES
    assert projected["candidate_posture"].startswith("candidate evidence")
    assert projected["retrieval_packet"]["evidence_hits"][0]["raw_ref"] == "raw:line:17"
    assert projected["retrieval_packet"]["evidence_hits"][0]["refs"]["segment"] == "segment-1.md#event-1"
    assert projected["route_traces"][0]["results"][0]["session_ref"] == "session:session-1"
    projected_provider_state = projected["retrieval_packet"]["provider"]["status"]["provider_states"]["portable_sqlite"]
    assert projected["retrieval_packet"]["provider"]["status"]["reasons"] == ["portable provider is stale"]
    assert projected_provider_state["reasons"] == ["freshness state is dirty"]
    assert projected_provider_state["freshness"]["reasons"] == ["freshness state is dirty"]
    assert projected_provider_state["freshness"]["diagnostics"] == ["projection_dirty"]
    assert "dirty_session_ids" not in projected_provider_state["freshness"]
    assert projected["freshness"]["ok"] is False
    assert projected["freshness"]["diagnostics"] == ["provider stale"]
    assert projected["freshness"]["provider"]["providers"]["portable_sqlite"]["status"] == "stale"
    assert projected["freshness"]["provider"]["reasons"] == ["portable provider is stale"]
    assert projected["freshness"]["provider"]["providers"]["portable_sqlite"]["reasons"] == [
        "freshness state is dirty"
    ]
    access = projected["mcp_access"]
    assert "retrieval_packet.provider" in access["compacted_collections"]
    assert "freshness.provider" in access["compacted_collections"]
    assert "retrieval_packet.provider.status.providers.portable_sqlite.metadata" in access["omitted_fields"]
    assert "x" * 100 not in json.dumps(projected, ensure_ascii=False)


def test_capability_projection_still_blocks_unknown_nested_evidence_packet_data() -> None:
    payload = {
        "schema": "aoa_session_memory_evidence_packet_v1",
        "ok": True,
        "candidate_posture": "candidate evidence",
        "retrieval_packet": {"unrecognized": {"body": "x" * 40_000}},
    }

    projected = _project_capability_output("aoa_session_evidence_packet", payload)

    assert projected["ok"] is False
    assert projected["error"] == "capability_output_limit_exceeded"
    assert projected["source_payload_bytes"] > 40_000


def test_capability_projection_fails_closed_above_output_ceiling() -> None:
    payload = {"ok": True, "unbounded": "x" * 40_000}

    projected = _project_capability_output("aoa_session_search", payload)

    assert projected["ok"] is False
    assert projected["error"] == "capability_output_limit_exceeded"
    assert projected["max_output_bytes"] == CAPABILITY_PROFILE_MAX_OUTPUT_BYTES


def test_capability_retrieve_projection_suppresses_only_control_echoes() -> None:
    payload = {
        "ok": True,
        "evidence_hits": [
            {
                "event_type": "TOOL_CALL",
                "title": "Tool call: exec",
                "raw_ref": "raw:line:10",
                "preview": "session.call_tool('aoa_session_retrieve', {'query': 'needle'})",
            },
            {
                "event_type": "USER_INTENT",
                "title": "User message",
                "raw_ref": "raw:line:20",
                "preview": "the actual user evidence",
            },
            {
                "event_type": "TOOL_CALL",
                "title": "Tool call: exec",
                "raw_ref": "raw:line:30",
                "preview": "pytest owner_test.py",
            },
        ],
        "mcp_access": {"mutates": False},
    }

    projected = _project_capability_retrieve_candidates(
        payload,
        requested_limit=2,
        candidate_limit=32,
    )

    assert [item["raw_ref"] for item in projected["evidence_hits"]] == [
        "raw:line:20",
        "raw:line:30",
    ]
    control = projected["mcp_access"]["consumer_candidate_projection"]
    assert control["suppressed_control_echo_count"] == 1
    assert control["suppressed_control_echo_refs"] == ["raw:line:10"]
    assert control["ordering"] == "owner_order_preserved"
