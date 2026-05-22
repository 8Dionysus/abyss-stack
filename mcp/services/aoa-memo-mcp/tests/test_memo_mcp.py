from __future__ import annotations

import json
import asyncio
from pathlib import Path

import pytest

from aoa_memo_mcp.core import AoAMemoMCPState
from aoa_memo_mcp.server import build_server


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
                "schema": {"const": "aoa_local_memo_receipt_v1"},
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
    assert "create or repair local memo port" not in route_only["recommended_route"]
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


def test_server_builds(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    assert build_server(tmp_path) is not None


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


def test_mcp_surface_contracts(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    server = build_server(tmp_path)

    async def inspect() -> tuple[set[str], set[str], set[str]]:
        tools = {tool.name for tool in await server.list_tools()}
        prompts = {prompt.name for prompt in await server.list_prompts()}
        templates = {template.uriTemplate for template in await server.list_resource_templates()}
        return tools, prompts, templates

    tools, prompts, templates = asyncio.run(inspect())
    assert tools == {
        "aoa_memo_build_port_index",
        "aoa_memo_brief",
        "aoa_memo_search",
        "aoa_memo_create_candidate",
        "aoa_memo_landing_plan",
        "aoa_memo_pending_exports",
        "aoa_memo_prepare_intake_packet",
        "aoa_memo_review_intake",
        "aoa_memo_validate_candidate",
        "aoa_memo_validate_port",
    }
    assert prompts == {"memo-brief", "memo-intake", "memo-landing-plan", "memo-review", "session-rehydrate"}
    assert templates == {
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
