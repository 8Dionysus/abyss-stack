from __future__ import annotations

import json
import asyncio
from pathlib import Path

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

    stack_port = root / "stack-source/memo"
    for rel in ["candidates", "receipts", "exports", "local"]:
        (stack_port / rel).mkdir(parents=True, exist_ok=True)
    (stack_port / "AGENTS.md").write_text("# Stack memo port\n", encoding="utf-8")
    (stack_port / "README.md").write_text("# Stack memo\n", encoding="utf-8")

    machine_port = root / "machine-state/memo"
    for rel in ["candidates", "receipts", "exports", "local"]:
        (machine_port / rel).mkdir(parents=True, exist_ok=True)
    (machine_port / "AGENTS.md").write_text("# Machine memo port\n", encoding="utf-8")
    (machine_port / "README.md").write_text("# Machine memo\n", encoding="utf-8")


def test_brief_reports_ready_port_and_contracts(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)
    brief = state.build_brief("Agents-of-Abyss", "test")

    assert brief["schema"] == "aoa_memo_brief_v1"
    assert brief["local_port"]["ready"] is True
    assert all(item["exists"] for item in brief["central_memory_contracts"])
    assert brief["operation_mode"] == "write_candidate_only"


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
    data["desired_route"] = "durable_memory"
    candidate.write_text(json.dumps(data), encoding="utf-8")
    invalid = state.validate_candidate(candidate)
    assert invalid["ok"] is False
    assert any("durable_memory" in error for error in invalid["errors"])


def test_candidate_creation_does_not_overwrite_same_claim(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)

    first = state.create_candidate("Agents-of-Abyss", ["docs/FEDERATION_RULES.md"], "same claim")
    second = state.create_candidate("Agents-of-Abyss", ["docs/FEDERATION_RULES.md"], "same claim")

    assert first["path"] != second["path"]
    assert Path(first["path"]).exists()
    assert Path(second["path"]).exists()


def test_resources_and_search(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = AoAMemoMCPState.discover(tmp_path)

    resource = state.read_resource("aoa-memo://brief/repo/Agents-of-Abyss")
    assert resource["repo"] == "Agents-of-Abyss"
    session = state.read_resource("aoa-memo://session/session-1/rehydrate")
    assert session["found"] is True
    search = state.search("poisoning", scope="central")
    assert search["hits"]


def test_session_rehydrate_ignores_malformed_registry_items(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    registry = tmp_path / ".aoa/session-registry.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["sessions"].insert(0, "malformed")
    registry.write_text(json.dumps(data), encoding="utf-8")
    state = AoAMemoMCPState.discover(tmp_path)

    assert state.build_session_rehydrate("missing")["found"] is False
    assert state.build_session_rehydrate("session-1")["found"] is True


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
        assert {item["path"] for item in status["required_dirs"]} == {
            "candidates",
            "receipts",
            "exports",
            "local",
        }


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
        "aoa_memo_brief",
        "aoa_memo_search",
        "aoa_memo_create_candidate",
        "aoa_memo_validate_candidate",
    }
    assert prompts == {"memo-brief", "memo-intake", "memo-review", "session-rehydrate"}
    assert templates == {
        "aoa-memo://brief/repo/{repo}",
        "aoa-memo://memory/object/{object_id}",
        "aoa-memo://session/{session_id}/rehydrate",
        "aoa-memo://repo/{repo}/local-port-status",
    }
