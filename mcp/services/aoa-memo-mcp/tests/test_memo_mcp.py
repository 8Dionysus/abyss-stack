from __future__ import annotations

import json
import asyncio
import hashlib
from pathlib import Path

import pytest

from aoa_memo_mcp.core import AoAMemoMCPState
from aoa_memo_mcp.server import build_server
from aoa_memo_mcp.server import CAPABILITY_PROFILE_ENV_VAR
from aoa_memo_mcp.organ_access import CANDIDATE_CAPABILITY_ID
from aoa_memo_mcp.organ_access import ORGAN_ACCESS_MANIFEST_ENV_VAR
from aoa_memo_mcp.organ_access import READ_CAPABILITY_ID


PROFILE_SHA = (
    "sha256:62f3a911b5ea7ca87e629a7bd65b6556dd7b8122189b3cd9664169e05562374f"
)
PROFILE_SEMANTIC_DIGEST = (
    "sha256:10ca6d8e7beab801995cfdb12b63192a32f2a8e59781cdaf883b369f9162fd8e"
)
POLICY_SHA = (
    "sha256:75d25070faa435a7094d29c8313d9e487a48600034cc62d2f9674015e0f5a537"
)


def canonical_digest(
    payload: dict,
    *,
    exclude: set[str] | None = None,
    ensure_ascii: bool = True,
) -> str:
    value = {
        key: item
        for key, item in payload.items()
        if key not in (exclude or set())
    }
    encoded = json.dumps(
        value,
        ensure_ascii=ensure_ascii,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def write_organ_access_manifest(path: Path) -> Path:
    def primitive(primitive_id: str, kind: str, mcp_name: str) -> dict:
        return {
            "primitive_id": primitive_id,
            "kind": kind,
            "mcp_name": mcp_name,
            "approval_required": False,
        }

    payload = {
        "schema_version": "aoa_memo_organ_access_v1",
        "organ_id": "aoa-memo",
        "source_owner": "aoa-memo",
        "access_runtime_owner": "abyss-stack",
        "admission_owner": "aoa-sdk",
        "proof_owner": "aoa-evals",
        "contains_secrets": False,
        "admission_asserted": False,
        "owner_acceptance_asserted": False,
        "proof_asserted": False,
        "effect_activation_authorized": False,
        "capabilities": [
            {
                "capability_id": READ_CAPABILITY_ID,
                "policy_family": "read",
                "credential_class": "memo-read",
                "process_contour": "read",
                "primitives": [
                    primitive("brief-reviewed-memory", "tool", "aoa_memo_recall_brief"),
                    primitive("recall-reviewed-memory", "tool", "aoa_memo_recall_reviewed"),
                    primitive("read-reviewed-object", "tool", "aoa_memo_read_object"),
                    primitive(
                        "open-reviewed-object",
                        "resource_template",
                        "aoa-memo://memory/object/{object_id}",
                    ),
                ],
            },
            {
                "capability_id": CANDIDATE_CAPABILITY_ID,
                "policy_family": "candidate",
                "credential_class": "memo-candidate",
                "process_contour": "candidate",
                "primitives": [
                    primitive("create-local-candidate", "tool", "aoa_memo_create_candidate"),
                    primitive("prepare-intake-packet", "tool", "aoa_memo_prepare_intake_packet"),
                    primitive(
                        "prepare-forwarding-receipt",
                        "tool",
                        "aoa_memo_prepare_forwarding_receipt",
                    ),
                ],
            },
        ],
        "guardrails": {
            "durable_corpus_write_allowed": False,
            "owner_acceptance_inference_allowed": False,
            "proof_inference_allowed": False,
            "hidden_mcp_chaining_allowed": False,
            "annotations_are_security_enforcement": False,
            "discovery_can_expand_write_roots": False,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def orientation_plan() -> dict:
    host_ref = {
        "owner_repo": "abyss-machine",
        "artifact_ref": "C18:test",
        "source_ref": "repo:abyss-machine/test#C18",
        "artifact_digest": "sha256:" + ("1" * 64),
        "schema_ref": "schemas/host-capability-snapshot-reference-C18.json",
        "schema_version": "1.0.0",
    }
    resource_ref = {
        **host_ref,
        "artifact_ref": "C19:test",
        "source_ref": "repo:abyss-machine/test#C19",
        "artifact_digest": "sha256:" + ("2" * 64),
        "schema_ref": "schemas/host-resource-storage-plan-reference-C19.json",
    }
    card = {
        "id": "memo.decision.test",
        "kind": "decision",
        "title": "Reviewed owner route",
        "summary": "Current reviewed owner route.",
        "temperature": "cool",
        "review_state": "confirmed",
        "current_recall_status": "preferred",
        "supersedes": [],
        "superseded_by": None,
        "replacement_ref": None,
        "contradiction_refs": [],
        "authority_kind": "human_reviewed",
        "source_kind": "reviewed_corpus",
        "scope_classes": ["repo", "workspace"],
        "primary_recall_modes": ["semantic"],
        "source_path": "memo/objects/decisions/test/object.json",
        "inspect_key": "memo.decision.test",
        "expand_key": "memo.decision.test",
    }
    capsule = {
        "id": "memo.decision.test",
        "kind": "decision",
        "title": "Reviewed owner route",
        "summary": "Current reviewed owner route.",
        "source_kind": "reviewed_corpus",
        "recall_posture_short": "preferred current recall",
        "trust_posture_short": "reviewed",
        "use_when_short": "owner orientation",
        "do_not_use_short": "not action authority",
        "strongest_next_source": "docs/owner-route.md",
        "source_path": "memo/objects/decisions/test/object.json",
    }
    content = {
        "card": card,
        "capsule": capsule,
        "expanded": None,
        "source_route": "docs/owner-route.md",
    }
    item = {
        "ordinal": 1,
        "selection_score": 120,
        **content,
        "estimated_tokens": 200,
        "content_digest": canonical_digest(content),
    }
    profile_ref = {
        "owner_repo": "aoa-memo",
        "artifact_ref": (
            "mechanics/consumer-handoff/parts/orchestrator-recall-alignment/"
            "examples/codex_owner_orientation_v0.consumer-profile.json"
        ),
        "source_ref": "repo:aoa-memo/profile",
        "artifact_digest": PROFILE_SHA,
        "schema_ref": "schemas/codex_owner_orientation_profile_v0.schema.json",
        "schema_version": "codex_owner_orientation_profile_v0",
    }
    surface_ref = {
        "owner_repo": "aoa-memo",
        "artifact_ref": "generated/memory-objects/test.json",
        "source_ref": "repo:aoa-memo/generated/memory-objects/test.json",
        "artifact_digest": "sha256:" + ("3" * 64),
        "schema_ref": "schemas/generated-surfaces/test.schema.json",
        "schema_version": "aoa_memo_memory_object_surfaces_v2",
    }
    plan = {
        "schema_version": "codex_owner_orientation_plan_v0",
        "plan_id": "orientation:test",
        "consumer_id": "codex_owner_orientation_v0",
        "consumer_mode": "bounded",
        "status": "bounded_memory",
        "recall_intent": {
            "contract_id": "C07",
            "intent_id": "intent:test",
            "consumer_id": "codex_owner_orientation_v0",
            "trigger_id": "operator-explicit-pull",
            "mode": "explicit_public_pull",
            "data_class": "D0",
            "risk_class": "R1",
            "effect_ceiling": "none",
            "action_use": "forbidden",
            "tenant_id": "owner-local",
            "anchor_id": "anchor:test",
            "anchor_ref": {"source_ref": "repo:aoa-memo/MEMORY_INDEX.md"},
            "anchor_freshness": {
                "expires_at": "2026-07-29T12:00:00Z"
            },
            "policy_pin": {
                "policy_id": "policy:aoa-memo:codex-owner-orientation:v0",
                "policy_version": "0",
                "policy_digest": POLICY_SHA,
            },
            "model_prompt_provider_pin": {
                "provider": "none",
                "model_id": "deterministic-lexical",
                "model_version": "1",
                "prompt_digest": "sha256:" + ("0" * 64),
            },
            "source_refs": [host_ref, resource_ref],
        },
        "profile_ref": profile_ref,
        "profile_digest": PROFILE_SEMANTIC_DIGEST,
        "query_digest": "sha256:" + ("4" * 64),
        "memory_object_catalog_version": 1,
        "memory_object_catalog_ref": surface_ref,
        "memory_object_capsules_ref": surface_ref,
        "memory_object_sections_ref": surface_ref,
        "selection_algorithm": "current-source-plus-deterministic-lexical-v1",
        "budget": {
            "max_items": 3,
            "max_estimated_tokens": 900,
            "expand": False,
        },
        "items": [item],
        "omissions": [],
        "host_capability_ref": host_ref,
        "host_resource_plan_ref": resource_ref,
        "planned_at": "2026-07-29T09:00:00Z",
        "expires_at": "2026-07-29T12:00:00Z",
        "no_memory_fallback": True,
        "memory_write_performed": False,
        "policy_promotion_performed": False,
        "effect_authority": "none",
        "action_use": "forbidden",
        "plan_digest": "sha256:" + ("0" * 64),
    }
    plan["plan_digest"] = canonical_digest(plan, exclude={"plan_digest"})
    return plan


def orientation_bundle(plan: dict) -> dict:
    result_refs = ["memory-result:memo.decision.test:1234567890abcdef"]
    packet = {
        "contract_id": "C08",
        "instance_id": "recall-packet:test",
        "owner": "aoa-memo",
        "validation_status": "valid",
        "result_mode": (
            "bounded_memory" if plan["status"] == "bounded_memory" else "silence"
        ),
        "result_refs": result_refs if plan["items"] else [],
        "object_pins": [{"object_ref": item["card"]["id"]} for item in plan["items"]],
        "action_use": "forbidden",
    }
    packet["content_digest"] = canonical_digest(
        packet,
        exclude={"content_digest"},
        ensure_ascii=False,
    )
    decision = {
        "contract_id": "C09",
        "instance_id": "intervention-decision:test",
        "decision_id": "intervention-decision:test",
        "owner": "aoa-memo",
        "validation_status": "valid",
        "recall_packet_ref": packet["instance_id"],
        "decision": (
            "bounded_observation" if plan["items"] else "silence"
        ),
        "effect_authority": "none",
        "observation_refs": packet["result_refs"],
    }
    decision["content_digest"] = canonical_digest(
        decision,
        exclude={"content_digest"},
        ensure_ascii=False,
    )
    bundle = {
        "schema_version": "codex_owner_orientation_memo_bundle_v0",
        "semantic_owner": "aoa-memo",
        "control_plane_owner": "aoa-sdk",
        "runtime_delivery_owner": "abyss-stack",
        "plan_ref": f"aoa-sdk:owner-orientation-plan:{plan['plan_id']}",
        "plan_digest": plan["plan_digest"],
        "recall_packet": packet,
        "intervention_decision": decision,
        "delivery_eligible": True,
        "effect_authority": "none",
        "action_use": "forbidden",
        "memory_write_performed": False,
        "bundle_digest": "sha256:" + ("0" * 64),
    }
    bundle["bundle_digest"] = canonical_digest(
        bundle,
        exclude={"bundle_digest"},
    )
    return bundle


def seed_workspace(root: Path) -> None:
    memo = root / "aoa-memo"
    for rel in [
        "docs/memory/MEMORY_OPERATION_CYCLE.md",
        "docs/memory/LIVING_MEMORY_TOPOLOGY.md",
        "docs/memory/LOCAL_MEMO_PORT_STANDARD.md",
        "docs/boundaries/MEMORY_WRITE_PATH_GUARDRAILS.md",
        "docs/posture/MEMORY_OPERATION_MODES.md",
        "mechanics/retention/docs/CONSOLIDATION_FORGETTING_OPERATION.md",
    ]:
        path = memo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\npoisoning lifecycle candidate\n", encoding="utf-8")
    registry = memo / "generated/memory/memo_registry.min.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"memory_object_kinds": ["claim", "decision"], "core_docs": ["MEMORY_OPERATION_CYCLE.md"]}), encoding="utf-8")
    object_path = memo / "memo/objects/decisions/2026/abyss-stack-aoa-memo-mcp-access-plane/object.json"
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_payload = {
        "id": "memo.decision.2026-05-22.abyss-stack-aoa-memo-mcp-access-plane",
        "kind": "decision",
        "title": "abyss-stack aoa-memo-mcp access plane route",
        "summary": "abyss-stack owns aoa-memo-mcp as an MCP access plane while aoa-memo remains durable authority.",
    }
    object_path.write_text(json.dumps(object_payload), encoding="utf-8")
    catalog = memo / "generated/memory-objects/memory_object_catalog.min.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(
        json.dumps(
            {
                "catalog_version": "test",
                "catalog_kind": "memory_object_catalog",
                "source_of_truth": ["memo/objects", "examples"],
                "memory_objects": [
                    {
                        **object_payload,
                        "scope_classes": ["repo", "workspace"],
                        "temperature": "cool",
                        "review_state": "confirmed",
                        "current_recall_status": "allowed",
                        "authority_kind": "human_reviewed",
                        "source_kind": "reviewed_corpus",
                        "primary_recall_modes": ["semantic", "source_route"],
                        "source_path": "memo/objects/decisions/2026/abyss-stack-aoa-memo-mcp-access-plane/object.json",
                        "inspect_key": object_payload["id"],
                        "expand_key": object_payload["id"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    seed_memory_port_schemas(memo)
    seed_indexing_vocabulary(memo)

    archive = root / ".aoa"
    session_dir = archive / "sessions/2026-05-19__001__example"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "AGENTS.md").write_text("# Session agents\n", encoding="utf-8")
    (session_dir / "SESSION.md").write_text("# Session\n", encoding="utf-8")
    (archive / "session-registry.json").write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "session_id": "session-1",
                        "display": {
                            "label": "2026-05-19__001__example",
                            "path": str(session_dir),
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    port = root / "Agents-of-Abyss/memo"
    for rel in ["candidates", "receipts", "exports", "local"]:
        (port / rel).mkdir(parents=True, exist_ok=True)
    (port / "AGENTS.md").write_text("# Memo port\n", encoding="utf-8")
    (port / "README.md").write_text("# Memo\n", encoding="utf-8")
    write_port_contract(port, "Agents-of-Abyss", "ecosystem")
    federation_rules = root / "Agents-of-Abyss/docs/FEDERATION_RULES.md"
    federation_rules.parent.mkdir(parents=True, exist_ok=True)
    federation_rules.write_text("# Federation rules\n", encoding="utf-8")

    stack_port = root / "stack-source/memo"
    for rel in ["candidates", "receipts", "exports", "local"]:
        (stack_port / rel).mkdir(parents=True, exist_ok=True)
    (stack_port / "AGENTS.md").write_text("# Stack memo port\n", encoding="utf-8")
    (stack_port / "README.md").write_text("# Stack memo\n", encoding="utf-8")
    write_port_contract(stack_port, "abyss-stack", "repo")
    stack_design = root / "stack-source/mcp/services/aoa-memo-mcp/DESIGN.md"
    stack_design.parent.mkdir(parents=True, exist_ok=True)
    stack_design.write_text("# aoa-memo-mcp design\n", encoding="utf-8")

    machine_port = root / "machine-state/memo"
    for rel in ["candidates", "receipts", "exports", "local"]:
        (machine_port / rel).mkdir(parents=True, exist_ok=True)
    (machine_port / "AGENTS.md").write_text("# Machine memo port\n", encoding="utf-8")
    (machine_port / "README.md").write_text("# Machine memo\n", encoding="utf-8")
    write_port_contract(machine_port, "abyss-machine", "host")
    seed_workspace_memory_map(root)


def seed_workspace_memory_map(root: Path) -> None:
    generated = root / "8Dionysus/generated"
    docs = root / "8Dionysus/docs"
    generated.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "8dionysus_workspace_memory_map_v1",
        "places": [
            {
                "name": "8Dionysus",
                "memory_role": "workspace-route-map-owner",
                "memory_route_status": "root_memory_route",
                "current_port_level": "route_only",
                "recommended_port_level": "route_only",
                "reviewed_memory_route": "aoa-memo:reviewed-intake",
                "evidence_route": ".aoa:retrieve/rehydrate/review-packet",
                "issues": [],
            },
            {
                "name": "aoa-memo",
                "memory_role": "reviewed-memory-owner",
                "memory_route_status": "root_memory_route",
                "current_port_level": "route_only",
                "recommended_port_level": "route_only",
                "reviewed_memory_route": "aoa-memo:reviewed-intake",
                "evidence_route": ".aoa:retrieve/rehydrate/review-packet",
                "issues": [],
            },
            {
                "name": ".aoa",
                "memory_role": "session-evidence-kernel",
                "memory_route_status": "session_evidence_route",
                "current_port_level": "route_only",
                "recommended_port_level": "route_only",
                "reviewed_memory_route": "aoa-memo:reviewed-intake",
                "evidence_route": ".aoa:retrieve/rehydrate/review-packet",
                "issues": [],
            },
            {
                "name": "Tree-of-Sophia",
                "memory_role": "local-memory-port-candidate",
                "memory_route_status": "root_memory_route",
                "current_port_level": "route_only",
                "recommended_port_level": "full_port",
                "reviewed_memory_route": "aoa-memo:reviewed-intake",
                "evidence_route": ".aoa:retrieve/rehydrate/review-packet",
                "issues": ["recommended full memo port not yet present"],
            },
            {
                "name": "Agents-of-Abyss",
                "memory_role": "local-memory-port-candidate",
                "memory_route_status": "local_port_route",
                "current_port_level": "full_port",
                "recommended_port_level": "full_port",
                "reviewed_memory_route": "aoa-memo:reviewed-intake",
                "evidence_route": ".aoa:retrieve/rehydrate/review-packet",
                "issues": [],
            },
        ],
    }
    generated.joinpath("workspace_memory_map.min.json").write_text(json.dumps(payload), encoding="utf-8")
    docs.joinpath("WORKSPACE_MEMORY_MAP.md").write_text(
        "# Workspace memory map\n\n.aoa session_evidence_route\nTree-of-Sophia route_only\n",
        encoding="utf-8",
    )


def add_workspace_full_port(root: Path, repo: str) -> None:
    map_path = root / "8Dionysus/generated/workspace_memory_map.min.json"
    payload = json.loads(map_path.read_text(encoding="utf-8"))
    payload["places"].append(
        {
            "name": repo,
            "memory_role": "local-memory-port-candidate",
            "memory_route_status": "local_port_route",
            "current_port_level": "full_port",
            "recommended_port_level": "full_port",
            "reviewed_memory_route": "aoa-memo:reviewed-intake",
            "evidence_route": ".aoa:retrieve/rehydrate/review-packet",
            "issues": [],
        }
    )
    map_path.write_text(json.dumps(payload), encoding="utf-8")


def seed_local_memo_port(root: Path, repo: str, source_ref: str) -> Path:
    port = root / repo / "memo"
    for rel in ["candidates", "receipts", "exports", "local"]:
        (port / rel).mkdir(parents=True, exist_ok=True)
    (port / "AGENTS.md").write_text(f"# {repo} memo port\n", encoding="utf-8")
    (port / "README.md").write_text(f"# {repo} memo\n", encoding="utf-8")
    write_port_contract(port, repo, "repo")
    source = root / repo / source_ref
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(f"# {repo} source\nrole memory handoff route\n", encoding="utf-8")
    return port


def seed_memory_port_schemas(memo: Path) -> None:
    schema_dir = memo / "schemas/memory-ports"
    schema_dir.mkdir(parents=True, exist_ok=True)
    common_string = {"type": "string", "minLength": 1}
    string_array = {"type": "array", "items": common_string}
    schemas = {
        "local_memo_candidate.schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema",
                "id",
                "repo",
                "kind",
                "family",
                "scope",
                "claim",
                "source_refs",
                "evidence_refs",
                "route",
                "review_state",
                "lifecycle",
                "source_trust",
                "operation_mode",
                "created_at",
                "guardrails",
            ],
            "properties": {
                "schema": {"const": "aoa_local_memo_candidate_v1"},
                "id": common_string,
                "repo": common_string,
                "kind": common_string,
                "family": common_string,
                "scope": common_string,
                "claim": common_string,
                "source_refs": {"type": "array", "minItems": 1, "items": common_string},
                "evidence_refs": {"type": "array", "minItems": 1, "items": common_string},
                "route": common_string,
                "review_state": common_string,
                "lifecycle": common_string,
                "source_trust": common_string,
                "operation_mode": common_string,
                "created_at": common_string,
                "risk": string_array,
                "guardrails": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["direct_durable_write", "instructions_treated_as_data"],
                    "properties": {
                        "direct_durable_write": {"type": "boolean"},
                        "instructions_treated_as_data": {"type": "boolean"},
                        "requires_reviewed_intake": {"type": "boolean"},
                    },
                },
                "notes": {"type": "string"},
            },
        },
        "local_memo_export.schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema",
                "id",
                "repo",
                "target_owner",
                "target_route",
                "candidate_refs",
                "receipt_refs",
                "source_refs",
                "evidence_refs",
                "allowed_result",
                "created_at",
            ],
            "properties": {
                "schema": {"const": "aoa_local_memo_export_v1"},
                "id": common_string,
                "repo": common_string,
                "target_owner": {"const": "aoa-memo"},
                "target_route": {"const": "reviewed_intake"},
                "candidate_refs": {"type": "array", "minItems": 1, "items": common_string},
                "receipt_refs": string_array,
                "source_refs": string_array,
                "evidence_refs": string_array,
                "allowed_result": common_string,
                "created_at": common_string,
                "notes": {"type": "string"},
            },
        },
        "local_memo_port.schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema",
                "repo",
                "owner",
                "stronger_memory_owner",
                "default_mode",
                "port_scope",
                "allowed_routes",
                "candidate_dir",
                "receipt_dir",
                "export_dir",
                "local_dir",
                "validators",
                "return_receipts",
            ],
            "properties": {
                "schema": {"const": "aoa_local_memo_port_v1"},
                "repo": common_string,
                "owner": common_string,
                "stronger_memory_owner": {"const": "aoa-memo"},
                "default_mode": common_string,
                "port_scope": common_string,
                "allowed_routes": {"type": "array", "minItems": 1, "items": common_string},
                "candidate_dir": {"const": "candidates"},
                "receipt_dir": {"const": "receipts"},
                "export_dir": {"const": "exports"},
                "local_dir": {"const": "local"},
                "validators": {"type": "array", "minItems": 1, "items": common_string},
                "return_receipts": {"type": "boolean"},
                "privacy_posture": {"type": "string"},
                "local_terms": {"type": "object"},
            },
        },
        "local_memo_port_index.schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema",
                "repo",
                "port",
                "default_mode",
                "counts",
                "by_kind",
                "by_family",
                "by_route",
                "open_items",
                "generated_at",
                "source_refs",
            ],
            "properties": {
                "schema": {"const": "aoa_local_memo_port_index_v1"},
                "repo": common_string,
                "port": common_string,
                "default_mode": common_string,
                "counts": {"type": "object"},
                "by_kind": {"type": "object"},
                "by_family": {"type": "object"},
                "by_route": {"type": "object"},
                "open_items": {"type": "array"},
                "generated_at": common_string,
                "source_refs": {"type": "array", "minItems": 1, "items": common_string},
            },
        },
        "local_memo_receipt.schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema", "id", "repo", "candidate_ref", "result", "route", "checks", "errors", "created_at"],
            "properties": {
                "schema": {"const": "aoa_local_memo_receipt_v2"},
                "id": common_string,
                "repo": common_string,
                "candidate_ref": common_string,
                "export_ref": common_string,
                "result": {"enum": ["validated", "rejected", "forwarded", "landed", "archived"]},
                "route": common_string,
                "checks": {"type": "array", "minItems": 1, "items": common_string},
                "errors": {"type": "array", "items": {"type": "string"}},
                "created_at": common_string,
                "checked_by": common_string,
                "notes": {"type": "string"},
            },
        },
    }
    for name, payload in schemas.items():
        (schema_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def seed_indexing_vocabulary(memo: Path) -> None:
    path = memo / "config/memory-ports/indexing_vocabulary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "aoa_memo_port_indexing_vocabulary_v1",
                "terms": {
                    "kind": ["decision", "route", "pattern", "lesson", "constraint", "incident", "preference", "checkpoint", "handoff"],
                    "family": ["memory-access", "runtime", "topology", "validation", "release", "agent-behavior", "provenance", "kag-bridge", "session-recovery"],
                    "scope": ["session", "repo", "workspace", "project", "ecosystem", "host", "agent"],
                    "route": ["local_only", "reviewed_intake", "owner_handoff", "quarantine", "archive"],
                    "review_state": ["candidate", "validated", "rejected", "forwarded", "reviewed", "landed", "superseded", "archived"],
                    "lifecycle": ["captured", "candidate", "reviewed", "current", "superseded", "retracted", "archived", "frozen"],
                    "source_trust": ["review_required", "reviewed_owner_source", "untrusted", "unknown", "derived", "generated"],
                    "risk": ["indirect_prompt_injection", "sleeper_memory", "poisoned_experience", "source_spoofing", "private_data_bleed", "instruction_as_content", "stale_context", "permission_leakage", "over_promotion", "hallucinated_merge"],
                },
            }
        ),
        encoding="utf-8",
    )


def write_port_contract(port: Path, repo: str, scope: str) -> None:
    (port / "PORT.yaml").write_text(
        "\n".join(
            [
                "schema: aoa_local_memo_port_v1",
                f"repo: {repo}",
                f"owner: {repo}",
                "stronger_memory_owner: aoa-memo",
                "default_mode: write_candidate_only",
                f"port_scope: {scope}",
                "allowed_routes:",
                "  - local_only",
                "  - reviewed_intake",
                "  - owner_handoff",
                "  - quarantine",
                "candidate_dir: candidates",
                "receipt_dir: receipts",
                "export_dir: exports",
                "local_dir: local",
                "validators:",
                "  - aoa_memo_validate_candidate",
                "  - validate_local_memo_port",
                "return_receipts: true",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_brief_reports_ready_port_and_contracts(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)
    brief = state.build_brief("Agents-of-Abyss", "test")

    assert brief["schema"] == "aoa_memo_brief_v1"
    assert brief["local_port"]["ready"] is True
    assert all(item["exists"] for item in brief["central_memory_contracts"])
    assert brief["operation_mode"] == "write_candidate_only"
    assert brief["workspace_memory_map"]["current_port_level"] == "full_port"


def test_brief_returns_reviewed_memory_for_repo(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)

    brief = state.build_brief("abyss-stack", "aoa-memo-mcp access plane")

    assert brief["reviewed_memory"]
    assert brief["reviewed_memory"][0]["id"] == "memo.decision.2026-05-22.abyss-stack-aoa-memo-mcp-access-plane"


def test_abyss_stack_route_fails_closed_when_source_checkout_is_missing(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    runtime_port = seed_local_memo_port(tmp_path, "abyss-stack", "DESIGN.md")
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "missing-stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)

    route = state.repo_route("abyss-stack")

    assert route.source_root is None
    assert route.memo_port is None
    with pytest.raises(ValueError, match="unknown repo or missing source root: abyss-stack"):
        state.create_candidate(
            "abyss-stack",
            ["DESIGN.md"],
            "Missing source checkout should not fall back to the runtime mirror",
        )
    assert not list((runtime_port / "candidates").glob("*.json"))


def test_brief_uses_workspace_memory_map_for_route_only_and_authority(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)

    route_only = state.build_brief("Tree-of-Sophia", "continuity")
    authority = state.build_brief("aoa-memo", "durable landing")
    session = state.build_brief(".aoa", "rehydrate")

    assert route_only["operation_mode"] == "read_only"
    assert route_only["workspace_memory_map"]["recommended_port_level"] == "full_port"
    assert route_only["memory_route"]["candidate"] == "no local candidate route until this place has a memo port"
    assert any("repo-local topology pass" in item for item in route_only["recommended_route"])
    assert "create local candidate under memo/candidates" not in route_only["recommended_route"]
    assert authority["operation_mode"] == "read_write_under_review"
    assert authority["owner_note"].startswith("reviewed memory authority")
    assert authority["memory_route"]["candidate"] == "aoa-memo source patch/review path; no repo-local candidate shortcut"
    assert authority["source_hierarchy"][1] == "aoa-memo authored reviewed memory contracts and generated read models"
    assert any("source patches" in item for item in authority["recommended_route"])
    assert session["operation_mode"] == "read_only"
    assert session["workspace_memory_map"]["memory_route_status"] == "session_evidence_route"
    assert session["memory_route"]["candidate"].startswith(".aoa carries session evidence")
    assert session["source_hierarchy"][1] == ".aoa session evidence and rehydration pointers, not a local memo port"


def test_candidate_creation_and_guardrail_validation(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)
    result = state.create_candidate(
        "Agents-of-Abyss",
        ["docs/FEDERATION_RULES.md"],
        "Route memory through reviewed candidate intake",
    )

    assert result["validation"]["ok"] is True
    candidate = Path(result["path"])
    data = json.loads(candidate.read_text(encoding="utf-8"))
    data["route"] = "durable_memory"
    candidate.write_text(json.dumps(data), encoding="utf-8")
    invalid = state.validate_candidate(candidate)
    assert invalid["ok"] is False
    assert any("durable_memory" in error for error in invalid["errors"])


def test_validate_candidate_rejects_path_outside_known_port(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    outside = tmp_path / "outside.candidate.json"
    outside.write_text(json.dumps({"schema": "aoa_local_memo_candidate_v1"}), encoding="utf-8")
    state = AoAMemoMCPState.discover(tmp_path)

    result = state.validate_candidate(outside)

    assert result["ok"] is False
    assert any("known local memo port" in error for error in result["errors"])


def test_invalid_vocabulary_does_not_write_candidate(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)

    result = state.create_candidate(
        "Agents-of-Abyss",
        ["docs/FEDERATION_RULES.md"],
        "Invalid vocabulary should not touch disk",
        family="private-taxonomy",
    )

    assert result["validation"]["ok"] is False
    assert any("unknown vocabulary term" in error for error in result["validation"]["errors"])
    assert not Path(result["path"]).exists()


def test_missing_central_vocabulary_returns_warning(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    (tmp_path / "aoa-memo/config/memory-ports/indexing_vocabulary.json").unlink()
    state = AoAMemoMCPState.discover(tmp_path)

    result = state.create_candidate(
        "Agents-of-Abyss",
        ["docs/FEDERATION_RULES.md"],
        "Fallback vocabulary should be visible",
    )

    assert result["validation"]["ok"] is True
    assert result["validation"]["warnings"] == ["central memo port vocabulary is missing; fallback terms were used"]


def test_schema_additional_properties_are_rejected(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)
    result = state.create_candidate(
        "Agents-of-Abyss",
        ["docs/FEDERATION_RULES.md"],
        "Schema should reject extra packet fields",
    )
    candidate = Path(result["path"])
    data = json.loads(candidate.read_text(encoding="utf-8"))
    data["extra"] = True
    candidate.write_text(json.dumps(data), encoding="utf-8")

    invalid = state.validate_candidate(candidate)

    assert invalid["ok"] is False
    assert any("Additional properties are not allowed" in error for error in invalid["errors"])


def test_candidate_creation_does_not_overwrite_same_claim(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)

    first = state.create_candidate("Agents-of-Abyss", ["docs/FEDERATION_RULES.md"], "same claim")
    second = state.create_candidate("Agents-of-Abyss", ["docs/FEDERATION_RULES.md"], "same claim")

    assert first["path"] != second["path"]
    assert Path(first["path"]).exists()
    assert Path(second["path"]).exists()


def test_candidate_creation_uses_schema_safe_packet_ids_for_non_ascii_claims(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)

    result = state.create_candidate(
        "Agents-of-Abyss",
        ["docs/FEDERATION_RULES.md"],
        "Память должна работать из любого места",
    )

    assert result["validation"]["ok"] is True
    assert result["candidate"]["id"].endswith("-memo")
    assert Path(result["path"]).name.endswith(".memo.candidate.json")


def test_workspace_map_full_ports_are_known_for_candidate_validation(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    source_ref = "docs/AGENT_MEMORY_POSTURE.md"
    seed_local_memo_port(tmp_path, "aoa-agents", source_ref)
    add_workspace_full_port(tmp_path, "aoa-agents")
    state = AoAMemoMCPState.discover(tmp_path)

    created = state.create_candidate(
        "aoa-agents",
        [source_ref],
        "aoa-agents owns role-layer memory handoff posture",
        family="agent-behavior",
    )

    assert created["validation"]["ok"] is True
    assert state.validate_candidate(created["path"])["ok"] is True
    ports_search = state.search("role-layer", scope="ports")
    assert any("aoa-agents" in hit["path"] for hit in ports_search["hits"])


def test_unregistered_memo_port_rejects_candidate_writes_before_file(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    source_ref = "docs/UNLISTED_MEMORY_POSTURE.md"
    port = seed_local_memo_port(tmp_path, "unlisted-repo", source_ref)
    state = AoAMemoMCPState.discover(tmp_path)

    with pytest.raises(ValueError, match="not registered as a known local memo port"):
        state.create_candidate(
            "unlisted-repo",
            [source_ref],
            "unregistered memo ports must not accept local candidates",
        )

    assert list((port / "candidates").glob("*.candidate.json")) == []


def test_route_only_workspace_surface_rejects_candidate_writes(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    source_ref = "docs/TREE_MEMORY_POSTURE.md"
    port = seed_local_memo_port(tmp_path, "Tree-of-Sophia", source_ref)
    state = AoAMemoMCPState.discover(tmp_path)
    brief = state.build_brief("Tree-of-Sophia", "route-only physical port")

    assert brief["local_port"]["ready"] is True
    assert brief["operation_mode"] == "read_only"
    assert brief["memory_route"]["candidate"] == (
        "read-only memory route; no local candidate writes from this MCP route"
    )
    assert "create local candidate under memo/candidates" not in brief["recommended_route"]
    assert any("do not create local candidates" in item for item in brief["recommended_route"])

    with pytest.raises(ValueError, match="read_only"):
        state.create_candidate(
            "Tree-of-Sophia",
            [source_ref],
            "route-only workspaces must not accept local candidates",
        )

    assert list((port / "candidates").glob("*.candidate.json")) == []


def test_path_like_repo_values_are_rejected(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)

    for repo in ("../../tmp", "/tmp", "nested/repo", r"nested\repo", ".", ".."):
        with pytest.raises(ValueError, match="not a path|repository name"):
            state.create_candidate(repo, ["docs/FEDERATION_RULES.md"], "must stay in managed memo ports")


def test_resources_and_search(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)

    resource = state.read_resource("aoa-memo://brief/repo/Agents-of-Abyss")
    assert resource["repo"] == "Agents-of-Abyss"
    session = state.read_resource("aoa-memo://session/session-1/rehydrate")
    assert session["found"] is True
    search = state.search("poisoning", scope="central")
    assert search["hits"]
    route_search = state.search("session_evidence_route", scope="all")
    assert route_search["hits"]
    corpus_search = state.search("access repo:abyss-stack kind:decision", scope="corpus")
    assert corpus_search["schema"] == "aoa_memo_search_v1"
    assert corpus_search["low_confidence"] is False
    assert corpus_search["hits"][0]["type"] == "memory_object"
    assert corpus_search["hits"][0]["source_kind"] == "reviewed_corpus"
    assert corpus_search["hits"][0]["id"] == "memo.decision.2026-05-22.abyss-stack-aoa-memo-mcp-access-plane"
    filter_only_search = state.search("repo:abyss-stack", scope="all", limit=5)
    assert filter_only_search["hits"]
    assert all(hit["type"] == "memory_object" for hit in filter_only_search["hits"])
    assert filter_only_search["hits"][0]["id"] == "memo.decision.2026-05-22.abyss-stack-aoa-memo-mcp-access-plane"
    filter_only_mismatch = state.search("repo:missing-repo", scope="all")
    assert filter_only_mismatch["hits"] == []
    assert filter_only_mismatch["low_confidence"] is True
    mismatch = state.search("access repo:abyss-stack kind:pattern", scope="corpus")
    assert mismatch["hits"] == []
    assert mismatch["low_confidence"] is True
    index = state.read_resource("aoa-memo://repo/Agents-of-Abyss/memo-port-index")
    assert index["index"]["repo"] == "Agents-of-Abyss"
    pending = state.read_resource("aoa-memo://repo/Agents-of-Abyss/pending-exports")
    assert pending["schema"] == "aoa_local_memo_pending_exports_v1"
    memory_object = state.read_resource("aoa-memo://memory/object/memo.decision.2026-05-22.abyss-stack-aoa-memo-mcp-access-plane")
    assert memory_object["found"] is True
    assert memory_object["matches"][0]["object"]["id"] == "memo.decision.2026-05-22.abyss-stack-aoa-memo-mcp-access-plane"


def test_session_rehydrate_ignores_malformed_registry_items(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    registry = tmp_path / ".aoa/session-registry.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["sessions"].insert(0, "malformed")
    registry.write_text(json.dumps(data), encoding="utf-8")
    state = AoAMemoMCPState.discover(tmp_path)

    assert state.build_session_rehydrate("missing")["found"] is False
    assert state.build_session_rehydrate("session-1")["found"] is True


def test_session_rehydrate_missing_archive_path_is_not_found(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    registry = tmp_path / ".aoa/session-registry.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["sessions"].append(
        {
            "session_id": "session-without-path",
            "display": {"label": "missing-path"},
        }
    )
    registry.write_text(json.dumps(data), encoding="utf-8")
    state = AoAMemoMCPState.discover(tmp_path)

    result = state.build_session_rehydrate("session-without-path")
    assert result["found"] is False
    assert result["reason"] == "session archive path is missing"
    assert "agents" not in result


def test_session_rehydrate_missing_archive_target_is_not_found(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    registry = tmp_path / ".aoa/session-registry.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["sessions"].append(
        {
            "session_id": "session-with-stale-path",
            "display": {"label": "stale-path", "path": "sessions/missing"},
        }
    )
    registry.write_text(json.dumps(data), encoding="utf-8")
    state = AoAMemoMCPState.discover(tmp_path)

    result = state.build_session_rehydrate("session-with-stale-path")
    assert result["found"] is False
    assert result["reason"] == "session archive path does not exist"
    assert "agents" not in result


def test_server_builds(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    server = build_server(tmp_path)
    assert server is not None
    assert server.application_version == "0.2.0"


def test_pilot_port_topology(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    monkeypatch.setenv("AOA_ABYSS_MACHINE_MEMO_ROOT", str(tmp_path / "machine-state/memo"))
    state = AoAMemoMCPState.discover(tmp_path)

    for repo in ("Agents-of-Abyss", "abyss-stack", "abyss-machine"):
        status = state.build_local_port_status(repo)
        assert status["ready"] is True
        assert status["port_contract_exists"] is True
        assert {item["path"] for item in status["required_dirs"]} == {
            "candidates",
            "receipts",
            "exports",
            "local",
        }


def test_port_index_validation_and_intake_review(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)

    created = state.create_candidate(
        "abyss-stack",
        ["mcp/services/aoa-memo-mcp/DESIGN.md"],
        "MCP should prepare local intake packets before aoa-memo landing",
    )
    assert created["validation"]["ok"] is True
    index = state.build_port_index("abyss-stack", write=True)
    assert index["written"] is True
    index_markdown = (tmp_path / "stack-source/memo/INDEX.md").read_text(encoding="utf-8")
    assert "## Agent Route" in index_markdown
    assert "## Validate" not in index_markdown
    assert state.validate_port("abyss-stack")["ok"] is True

    export = state.prepare_intake_packet("abyss-stack", [created["local_ref"]])
    assert export["ok"] is True
    reviewed = state.review_intake(export["path"])
    assert reviewed["ok"] is True
    assert Path(reviewed["receipt_path"]).exists()
    assert reviewed["receipt"]["schema"] == "aoa_local_memo_receipt_v2"
    assert reviewed["receipt"]["result"] == "forwarded"
    assert reviewed["receipt"]["checked_by"] == "aoa-memo-mcp"
    assert "reviewed_by" not in reviewed["receipt"]


def test_pending_exports_and_landing_plan(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)
    created = state.create_candidate(
        "abyss-stack",
        ["mcp/services/aoa-memo-mcp/DESIGN.md"],
        "MCP should expose landing readiness without durable writes",
    )
    export = state.prepare_intake_packet("abyss-stack", [created["local_ref"]])
    reviewed = state.review_intake(export["path"])
    export_path = Path(export["path"])
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    payload["allowed_result"] = "reviewed_write"
    payload["receipt_refs"] = [Path(reviewed["receipt_path"]).relative_to(tmp_path / "stack-source/memo").as_posix()]
    export_path.write_text(json.dumps(payload), encoding="utf-8")

    pending = state.list_pending_exports("abyss-stack")
    plan = state.build_landing_plan("abyss-stack", export_path.relative_to(tmp_path / "stack-source/memo").as_posix())

    assert pending["counts"]["ready"] == 1
    assert pending["exports"][0]["landing_state"] == "ready"
    assert plan["ok"] is True
    assert plan["dry_run_command"][0:2] == ["python", "scripts/memory/land_reviewed_memo_intake.py"]
    assert plan["authority_note"].startswith("MCP prepares")


def test_landing_plan_blocks_missing_export_evidence_ref(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)
    created = state.create_candidate(
        "abyss-stack",
        ["mcp/services/aoa-memo-mcp/DESIGN.md"],
        "MCP should block landing readiness when export evidence refs disappear",
    )
    export = state.prepare_intake_packet("abyss-stack", [created["local_ref"]])
    reviewed = state.review_intake(export["path"])
    export_path = Path(export["path"])
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    payload["allowed_result"] = "reviewed_write"
    payload["receipt_refs"] = [Path(reviewed["receipt_path"]).relative_to(tmp_path / "stack-source/memo").as_posix()]
    payload["evidence_refs"] = ["mcp/services/aoa-memo-mcp/MISSING.md"]
    export_path.write_text(json.dumps(payload), encoding="utf-8")

    plan = state.build_landing_plan("abyss-stack", export_path.relative_to(tmp_path / "stack-source/memo").as_posix())

    assert plan["ok"] is False
    assert plan["readiness"]["landing_state"] == "blocked"
    assert any("evidence_refs[0] points to missing ref" in error for error in plan["errors"])


def test_landing_plan_reports_missing_export_id(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)

    plan = state.build_landing_plan("abyss-stack", "export:abyss-stack:missing")

    assert plan["schema"] == "aoa_memo_landing_plan_v1"
    assert plan["ok"] is False
    assert plan["export_ref"] == "export:abyss-stack:missing"
    assert any("export ref not found" in error for error in plan["errors"])


def test_invalid_export_packet_keeps_pending_and_brief_shapes(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    export_path = tmp_path / "stack-source/memo/exports/broken.json"
    export_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    state = AoAMemoMCPState.discover(tmp_path)

    pending = state.list_pending_exports("abyss-stack")
    status = state.build_local_port_status("abyss-stack")
    brief = state.build_brief("abyss-stack", "landing readiness")

    assert pending["ok"] is True
    assert pending["counts"] == {"total": 1, "pending": 1, "ready": 0, "landed": 0}
    assert pending["exports"][0]["landing_state"] == "invalid"
    assert pending["exports"][0]["ready_for_landing"] is False
    assert any("not a JSON object" in error for error in pending["exports"][0]["errors"])
    assert status["pending_exports"] == pending["counts"]
    assert brief["local_intake"]["pending_exports"] == 1
    assert brief["local_intake"]["ready_exports"] == 0


def test_landing_plan_blocks_missing_candidate_source_ref(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)
    created = state.create_candidate(
        "abyss-stack",
        ["mcp/services/aoa-memo-mcp/DESIGN.md"],
        "MCP should block landing readiness when candidate source refs disappear",
    )
    candidate_path = Path(created["path"])
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["source_refs"] = ["mcp/services/aoa-memo-mcp/MISSING.md"]
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    export = state.prepare_intake_packet("abyss-stack", [created["local_ref"]])

    assert export["ok"] is False
    assert any("source_refs[0] points to missing ref" in error for error in export["errors"])


def test_uri_scheme_payload_refs_are_symbolic_for_intake_and_landing_plan(
    tmp_path: Path, monkeypatch
) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)
    created = state.create_candidate(
        "abyss-stack",
        ["mcp/services/aoa-memo-mcp/DESIGN.md"],
        "MCP should preserve non-local URI refs as symbolic handles",
    )
    candidate_path = Path(created["path"])
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["source_refs"] = ["urn:aoa:memo:3"]
    candidate["evidence_refs"] = ["git+ssh://github.com/8Dionysus/aoa-memo.git#main"]
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    validation = state.validate_candidate(candidate_path)
    export = state.prepare_intake_packet("abyss-stack", [created["local_ref"]])
    reviewed = state.review_intake(export["path"])
    export_path = Path(export["path"])
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    payload["allowed_result"] = "reviewed_write"
    payload["receipt_refs"] = [
        Path(reviewed["receipt_path"]).relative_to(tmp_path / "stack-source/memo").as_posix()
    ]
    export_path.write_text(json.dumps(payload), encoding="utf-8")
    plan = state.build_landing_plan(
        "abyss-stack",
        export_path.relative_to(tmp_path / "stack-source/memo").as_posix(),
    )

    assert validation["ok"] is True
    assert export["ok"] is True
    assert reviewed["ok"] is True
    assert plan["ok"] is True


def test_colon_suffixed_local_payload_refs_are_checked(
    tmp_path: Path, monkeypatch
) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    readme = tmp_path / "stack-source/README.md"
    readme.write_text("# Stack source\n", encoding="utf-8")
    state = AoAMemoMCPState.discover(tmp_path)

    valid = state.create_candidate(
        "abyss-stack",
        ["README.md:12"],
        "MCP should treat line-suffixed local refs as checked local paths",
    )
    missing = state.create_candidate(
        "abyss-stack",
        ["MISSING.md:12"],
        "MCP should reject missing line-suffixed local refs",
    )

    assert valid["validation"]["ok"] is True
    assert missing["validation"]["ok"] is False
    assert any(
        "evidence_refs[0] points to missing ref MISSING.md:12" in error
        for error in missing["validation"]["errors"]
    )


def test_absolute_candidate_refs_are_rejected_for_intake(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)
    created = state.create_candidate(
        "abyss-stack",
        ["mcp/services/aoa-memo-mcp/DESIGN.md"],
        "Absolute packet refs should not cross port boundaries",
    )

    result = state.prepare_intake_packet("abyss-stack", [created["path"]])

    assert result["ok"] is False
    assert any("relative to the memo port" in error for error in result["errors"])
    assert not list((tmp_path / "stack-source/memo/exports").glob("*.aoa-memo-intake.json"))


def test_review_intake_rejects_export_path_outside_known_port(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    outside = tmp_path / "outside-export.json"
    outside.write_text(
        json.dumps(
            {
                "schema": "aoa_local_memo_export_v1",
                "id": "export:abyss-stack:20260520T171200Z:outside",
                "repo": "abyss-stack",
                "target_owner": "aoa-memo",
                "target_route": "reviewed_intake",
                "candidate_refs": ["candidates/missing.json"],
                "receipt_refs": [],
                "source_refs": ["mcp/services/aoa-memo-mcp/DESIGN.md"],
                "evidence_refs": ["mcp/services/aoa-memo-mcp/DESIGN.md"],
                "allowed_result": "candidate_only",
                "created_at": "2026-05-20T17:12:00Z",
            }
        ),
        encoding="utf-8",
    )
    state = AoAMemoMCPState.discover(tmp_path)

    result = state.review_intake(outside)

    assert result["ok"] is False
    assert any("known local memo port" in error for error in result["errors"])


def test_review_intake_returns_rejection_for_unknown_export_repo(tmp_path: Path, monkeypatch) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)
    created = state.create_candidate(
        "abyss-stack",
        ["mcp/services/aoa-memo-mcp/DESIGN.md"],
        "Unknown export repos should reject without crashing",
    )
    export = state.prepare_intake_packet("abyss-stack", [created["local_ref"]])
    export_path = Path(export["path"])
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    payload["repo"] = "unknown-repo"
    export_path.write_text(json.dumps(payload), encoding="utf-8")

    result = state.review_intake(export_path)

    assert result["ok"] is False
    assert result["receipt"]["result"] == "rejected"
    assert Path(result["receipt_path"]).exists()
    assert any("export repo does not resolve to a known memo port" in error for error in result["errors"])
    assert state.build_port_index("abyss-stack", check=True)["ok"] is True
    index = json.loads((tmp_path / "stack-source/memo/index.min.json").read_text(encoding="utf-8"))
    receipt_ref = Path(result["receipt_path"]).relative_to(tmp_path / "stack-source/memo").as_posix()
    assert index["counts"]["receipts"] == 1
    assert receipt_ref in index["source_refs"]


def test_mcp_surface_contracts(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    read_server = build_server(tmp_path, policy_family="read")
    candidate_server = build_server(tmp_path, policy_family="candidate")

    async def inspect(server) -> tuple[dict[str, object], set[str], set[str]]:
        tool_records = {
            tool.name: tool.annotations
            for tool in await server.list_tools()
        }
        tools = {tool.name for tool in await server.list_tools()}
        prompts = {prompt.name for prompt in await server.list_prompts()}
        templates = {template.uri_template for template in await server.list_resource_templates()}
        assert tools == set(tool_records)
        return tool_records, prompts, templates

    read_tools, read_prompts, read_templates = asyncio.run(
        inspect(read_server)
    )
    candidate_tools, candidate_prompts, candidate_templates = asyncio.run(
        inspect(candidate_server)
    )
    assert set(read_tools) == {
        "aoa_memo_recall_brief",
        "aoa_memo_recall_reviewed",
        "aoa_memo_read_object",
        "aoa_memo_build_port_index",
        "aoa_memo_brief",
        "aoa_memo_owner_orientation",
        "aoa_memo_search",
        "aoa_memo_landing_plan",
        "aoa_memo_pending_exports",
        "aoa_memo_validate_candidate",
        "aoa_memo_validate_port",
    }
    assert set(candidate_tools) == {
        "aoa_memo_create_candidate",
        "aoa_memo_prepare_forwarding_receipt",
        "aoa_memo_prepare_intake_packet",
        "aoa_memo_review_intake",
        "aoa_memo_write_port_index",
    }
    assert set(read_tools).isdisjoint(candidate_tools)
    for tool_annotations in read_tools.values():
        assert tool_annotations.read_only_hint is True
        assert tool_annotations.destructive_hint is False
        assert tool_annotations.idempotent_hint is True
        assert tool_annotations.open_world_hint is False
    for tool_annotations in candidate_tools.values():
        assert tool_annotations.read_only_hint is False
        assert tool_annotations.destructive_hint is True
        assert tool_annotations.idempotent_hint is False
        assert tool_annotations.open_world_hint is False
    assert read_prompts == {
        "memo-brief",
        "memo-landing-plan",
        "session-rehydrate",
    }
    assert candidate_prompts == {"memo-intake", "memo-review"}
    assert read_templates == {
        "aoa-memo://brief/repo/{repo}",
        "aoa-memo://memory/object/{object_id}",
        "aoa-memo://session/{session_id}/rehydrate",
        "aoa-memo://repo/{repo}/local-port-status",
        "aoa-memo://repo/{repo}/memo-port-index",
        "aoa-memo://repo/{repo}/memo-open-items",
        "aoa-memo://repo/{repo}/pending-exports",
        "aoa-memo://repo/{repo}/memo-vocabulary",
        "aoa-memo://intake/{packet_id}/review",
    }
    assert candidate_templates == set()


def test_owner_capability_profiles_remove_legacy_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = write_organ_access_manifest(tmp_path / "organ-access.v1.json")
    monkeypatch.setenv(ORGAN_ACCESS_MANIFEST_ENV_VAR, str(manifest))

    monkeypatch.setenv(CAPABILITY_PROFILE_ENV_VAR, READ_CAPABILITY_ID)
    read_server = build_server(tmp_path, policy_family="read")
    assert set(read_server._tool_manager._tools) == {
        "aoa_memo_recall_brief",
        "aoa_memo_recall_reviewed",
        "aoa_memo_read_object",
    }
    assert read_server._resource_manager._resources == {}
    assert {
        str(item.uri_template)
        for item in read_server._resource_manager._templates.values()
    } == {"aoa-memo://memory/object/{object_id}"}
    assert read_server._prompt_manager._prompts == {}

    monkeypatch.setenv(CAPABILITY_PROFILE_ENV_VAR, CANDIDATE_CAPABILITY_ID)
    candidate_server = build_server(tmp_path, policy_family="candidate")
    assert set(candidate_server._tool_manager._tools) == {
        "aoa_memo_create_candidate",
        "aoa_memo_prepare_intake_packet",
        "aoa_memo_prepare_forwarding_receipt",
    }
    assert candidate_server._resource_manager._resources == {}
    assert candidate_server._resource_manager._templates == {}
    assert candidate_server._prompt_manager._prompts == {}


def test_capability_profile_rejects_wrong_process_contour(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = write_organ_access_manifest(tmp_path / "organ-access.v1.json")
    monkeypatch.setenv(ORGAN_ACCESS_MANIFEST_ENV_VAR, str(manifest))
    monkeypatch.setenv(CAPABILITY_PROFILE_ENV_VAR, CANDIDATE_CAPABILITY_ID)

    with pytest.raises(SystemExit, match="must be 'durable-memory-read'"):
        build_server(tmp_path, policy_family="read")


def test_reviewed_access_methods_exclude_local_and_registry_fallbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(tmp_path / "stack-source"))
    state = AoAMemoMCPState.discover(tmp_path)

    brief = state.build_reviewed_brief("abyss-stack", "access plane")
    assert brief["schema"] == "aoa_memo_reviewed_brief_v1"
    assert brief["reviewed_memory"]
    assert brief["candidate_route_exposed"] is False
    assert "local_port" not in brief
    assert "local_intake" not in brief

    object_id = brief["reviewed_memory"][0]["id"]
    reviewed = state.build_reviewed_memory_object(object_id)
    missing = state.build_reviewed_memory_object("memory-object-kinds")
    assert reviewed["found"] is True
    assert all(item["source_kind"] == "reviewed_corpus" for item in reviewed["matches"])
    assert missing["found"] is False
    assert missing["matches"] == []

    search = state.search("access plane", scope="reviewed", limit=8)
    assert all(item.get("type") == "memory_object" for item in search["hits"])
    assert all(item.get("source_kind") == "reviewed_corpus" for item in search["hits"])


def test_mcp_policy_family_and_candidate_root_gate_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seed_workspace(tmp_path)
    monkeypatch.setenv(
        "AOA_ABYSS_STACK_ROOT",
        str(tmp_path / "stack-source"),
    )
    state = AoAMemoMCPState.discover(tmp_path)
    args = (
        "abyss-stack",
        ["mcp/services/aoa-memo-mcp/DESIGN.md"],
        "Policy isolation must deny memo writes from the read contour",
    )

    monkeypatch.setenv("AOA_MCP_POLICY_FAMILY", "read")
    with pytest.raises(PermissionError, match="read contour"):
        state.create_candidate(*args)

    monkeypatch.setenv("AOA_MCP_POLICY_FAMILY", "candidate")
    monkeypatch.delenv("AOA_MEMO_MCP_CANDIDATE_ROOTS", raising=False)
    with pytest.raises(
        PermissionError,
        match="AOA_MEMO_MCP_CANDIDATE_ROOTS",
    ):
        state.create_candidate(*args)

    allowed_root = tmp_path / "stack-source" / "memo"
    monkeypatch.setenv(
        "AOA_MEMO_MCP_CANDIDATE_ROOTS",
        str(allowed_root),
    )
    result = state.create_candidate(*args)
    assert Path(result["path"]).is_file()
    assert Path(result["path"]).is_relative_to(allowed_root)


def test_owner_orientation_delivers_without_reselection_or_persistence(
    tmp_path: Path,
) -> None:
    state = AoAMemoMCPState.discover(tmp_path)
    plan = orientation_plan()
    bundle = orientation_bundle(plan)

    result = state.deliver_owner_orientation(
        plan=plan,
        memo_bundle=bundle,
        observed_at="2026-07-29T09:30:00Z",
    )

    assert result["delivery_state"] == "delivered"
    assert [item["object_id"] for item in result["memory_payload"]] == [
        "memo.decision.test"
    ]
    assert result["reranking_performed"] is False
    assert result["reselection_performed"] is False
    assert result["persistence_performed"] is False
    assert result["effect_authority"] == "none"
    receipt = result["runtime_receipt"]
    assert receipt["contract_id"] == "C20"
    assert receipt["result"]["reason_code"] == "delivery_confirmed"
    assert receipt["content_minimization"]["memory_content_persisted"] is False
    assert receipt["authority"]["memory_semantic_authority"] is False


def test_owner_orientation_no_memory_mode_and_expiry_walk_back_cleanly(
    tmp_path: Path,
) -> None:
    state = AoAMemoMCPState.discover(tmp_path)
    plan = orientation_plan()
    plan.update(
        {
            "consumer_mode": "off",
            "status": "off",
            "budget": None,
            "items": [],
        }
    )
    plan["plan_digest"] = canonical_digest(plan, exclude={"plan_digest"})
    bundle = orientation_bundle(plan)

    suppressed = state.deliver_owner_orientation(
        plan=plan,
        memo_bundle=bundle,
        observed_at="2026-07-29T09:30:00Z",
    )
    bounded_plan = orientation_plan()
    expired = state.deliver_owner_orientation(
        plan=bounded_plan,
        memo_bundle=orientation_bundle(bounded_plan),
        observed_at="2026-07-29T12:00:00Z",
        attempt_no=2,
    )

    assert suppressed["delivery_state"] == "suppressed"
    assert suppressed["memory_payload"] == []
    assert suppressed["runtime_receipt"]["result"]["reason_code"] == (
        "policy_silence"
    )
    assert expired["delivery_state"] == "expired"
    assert expired["memory_payload"] == []
    assert expired["runtime_receipt"]["admission"]["state"] == "expired"


def test_owner_orientation_fails_closed_on_content_or_host_drift(
    tmp_path: Path,
) -> None:
    state = AoAMemoMCPState.discover(tmp_path)
    plan = orientation_plan()
    bundle = orientation_bundle(plan)
    plan["items"][0]["card"]["summary"] = "tampered"
    plan["plan_digest"] = canonical_digest(plan, exclude={"plan_digest"})
    bundle["plan_digest"] = plan["plan_digest"]
    bundle["bundle_digest"] = canonical_digest(
        bundle,
        exclude={"bundle_digest"},
    )

    with pytest.raises(ValueError, match="item content digest"):
        state.deliver_owner_orientation(
            plan=plan,
            memo_bundle=bundle,
            observed_at="2026-07-29T09:30:00Z",
        )

    plan = orientation_plan()
    plan["host_resource_plan_ref"]["artifact_ref"] = "host:test"
    plan["host_resource_plan_ref"]["source_ref"] = "repo:abyss-machine/test"
    plan["host_resource_plan_ref"]["schema_ref"] = "schemas/host.json"
    plan["plan_digest"] = canonical_digest(plan, exclude={"plan_digest"})
    bundle = orientation_bundle(plan)
    with pytest.raises(ValueError, match="C19"):
        state.deliver_owner_orientation(
            plan=plan,
            memo_bundle=bundle,
            observed_at="2026-07-29T09:30:00Z",
        )
