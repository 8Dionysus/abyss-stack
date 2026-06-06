from __future__ import annotations

import json
from pathlib import Path

from aoa_decisions_mcp.core import AoADecisionsMCPState
from aoa_decisions_mcp.server import build_server


STACK_ROOT = Path(__file__).resolve().parents[4]


def write_decision(
    repo_root: Path,
    decision_id: str,
    title: str,
    source_surface: str,
    route_anchor: str | None = None,
) -> None:
    metadata = [
        f"- Decision ID: {decision_id}",
        "- Original date: 2026-06-04",
        "- Surface classes: docs route",
        "- Guard families: decision graph",
    ]
    if route_anchor is not None:
        metadata.append(f"- Route anchors: {route_anchor}")
    metadata.append("- Posture: accepted")
    path = repo_root / "docs" / "decisions" / f"{decision_id}-test.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                "## Index Metadata",
                "",
                *metadata,
                "",
                "## Context",
                "",
                "A decision exists.",
                "",
                "## Source surfaces",
                "",
                f"- `{source_surface}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def seed_workspace(root: Path) -> None:
    repo = root / "repo-a"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "decisions" / "indexes").mkdir(parents=True)
    (repo / "docs" / "decisions" / "indexes" / "README.md").write_text("# Index\n", encoding="utf-8")
    write_decision(repo, "AAA-D-0001", "First Decision", "docs/source.md", route_anchor="config/app.toml")


def state_for(root: Path) -> AoADecisionsMCPState:
    return AoADecisionsMCPState.discover(
        workspace_root=root,
        stack_root=STACK_ROOT,
        output_dir=root / "graph",
        include_stack_repo=False,
    )


def test_status_auto_refreshes_graph_cache(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)

    status = state.ensure_fresh()

    assert status["status"] == "refreshed"
    assert status["decision_count"] == 1
    assert (tmp_path / "graph" / "workspace_decision_graph.json").is_file()
    assert (tmp_path / "graph" / "nodes.jsonl").is_file()
    assert (tmp_path / "graph" / "edges.jsonl").is_file()


def test_status_rebuilds_when_decision_lane_changes(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)
    first = state.summary()
    write_decision(tmp_path / "repo-a", "AAA-D-0002", "Second Decision", "docs/other.md")

    second = state.summary()

    assert first["decision_count"] == 1
    assert second["decision_count"] == 2
    assert first["input_fingerprint"] != second["input_fingerprint"]
    assert second["freshness"]["refreshed"] is True


def test_search_and_packet_return_graph_context(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)

    search = state.search("First", limit=5)
    packet = state.packet(query="First", repo="repo-a")

    assert search["count"] == 1
    assert search["results"][0]["label"] == "AAA-D-0001"
    assert packet["decision_count"] == 1
    assert any(edge["type"] == "CITES_SOURCE_SURFACE" for edge in packet["edges"])
    assert packet["authority_order"][0] == "repo-local docs/decisions/*.md"


def test_impact_packets_return_surface_and_issue_context(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)

    source_packet = state.source_surface("docs/source.md", repo="repo-a")
    owner_packet = state.owner_surface("docs/decisions/", repo="repo-a")
    changed_packet = state.changed_path("docs/source.md", repo="repo-a")
    symmetry_packet = state.repo_symmetry(repo="repo-a")
    issues_packet = state.issues(repo="repo-a")

    assert source_packet["schema"] == "aoa_decisions_source_surface_packet_v1"
    assert source_packet["decision_count"] == 1
    assert owner_packet["schema"] == "aoa_decisions_owner_surface_packet_v1"
    assert owner_packet["decision_count"] == 1
    assert changed_packet["schema"] == "aoa_decisions_changed_path_packet_v1"
    assert changed_packet["decision_count"] == 1
    assert symmetry_packet["schema"] == "aoa_decisions_repo_symmetry_packet_v1"
    assert symmetry_packet["repos"][0]["repo"] == "repo-a"
    assert symmetry_packet["repos"][0]["symmetry_note"] == "compare coverage posture; do not force identical repo structure"
    assert issues_packet["schema"] == "aoa_decisions_issues_packet_v1"
    assert issues_packet["issue_count"] == 0


def test_path_packets_include_route_anchor_impacts(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)

    changed_packet = state.changed_path("config/app.toml", repo="repo-a")
    packet = state.packet(path="config/app.toml", repo="repo-a")

    assert changed_packet["decision_count"] == 1
    assert changed_packet["decisions"][0]["label"] == "AAA-D-0001"
    assert any(surface.get("facet_key") == "Route anchors" for surface in changed_packet["surfaces"])
    assert any(edge["type"] == "HAS_DECISION_FACET" for edge in changed_packet["edges"])
    assert packet["decision_count"] == 1
    assert packet["decisions"][0]["label"] == "AAA-D-0001"
    assert any(edge["type"] == "HAS_DECISION_FACET" for edge in packet["edges"])


def test_resources_and_server_build(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)

    summary = state.read_resource("aoa-decisions://summary")
    decision = state.read_resource("aoa-decisions://decision/AAA-D-0001")
    issues = state.read_resource("aoa-decisions://issues")

    assert summary["decision_count"] == 1
    assert decision["matches"][0]["label"] == "AAA-D-0001"
    assert issues["issue_count"] == 0
    assert json.loads(state.render_resource("aoa-decisions://status"))["decision_count"] == 1
    assert build_server(workspace_root=tmp_path, stack_root=STACK_ROOT, output_dir=tmp_path / "graph") is not None
