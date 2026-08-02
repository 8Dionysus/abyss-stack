from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

import aoa_decisions_mcp.core as core
from aoa_decisions_mcp.core import AoADecisionsMCPState, DecisionGraphCacheUnavailable
from aoa_decisions_mcp.server import build_server


STACK_ROOT = Path(__file__).resolve().parents[4]


def test_default_stack_root_is_current_checkout() -> None:
    source = Path(core.__file__).read_text(encoding="utf-8")

    assert core.DEFAULT_STACK_ROOT == STACK_ROOT
    assert 'Path("/home/dionysus/src/abyss-stack")' not in source


def test_installed_entrypoint_discovers_checkout_from_cwd(tmp_path: Path) -> None:
    installed_core = (
        tmp_path
        / "venv"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "aoa_decisions_mcp"
        / "core.py"
    )
    installed_core.parent.mkdir(parents=True)
    installed_core.write_text("# installed package file\n", encoding="utf-8")
    checkout = tmp_path / "checkout" / "abyss-stack"
    builder = checkout / "scripts" / "build_workspace_decision_graph.py"
    builder.parent.mkdir(parents=True)
    builder.write_text("# builder\n", encoding="utf-8")
    cwd = checkout / "mcp" / "services"
    cwd.mkdir(parents=True)

    assert (
        core.discover_stack_root(package_file=installed_core, cwd=cwd)
        == checkout.resolve()
    )


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


def git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def initialize_tracked_git_repo(repo_root: Path) -> None:
    git(repo_root, "init", "--initial-branch=main")
    git(repo_root, "config", "user.name", "AoA Test")
    git(repo_root, "config", "user.email", "aoa-test@example.invalid")
    git(
        repo_root,
        "remote",
        "add",
        "origin",
        f"https://github.com/example/{repo_root.name}.git",
    )
    git(repo_root, "add", ".")
    git(repo_root, "commit", "-m", "seed")
    git(repo_root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(
        repo_root,
        "symbolic-ref",
        "refs/remotes/origin/HEAD",
        "refs/remotes/origin/main",
    )


def seed_workspace(root: Path) -> None:
    repo = root / "repo-a"
    repo.mkdir(parents=True)
    (repo / "docs" / "decisions" / "indexes").mkdir(parents=True)
    (repo / "docs" / "decisions" / "indexes" / "README.md").write_text(
        "# Index\n", encoding="utf-8"
    )
    write_decision(
        repo,
        "AAA-D-0001",
        "First Decision",
        "docs/source.md",
        route_anchor="config/app.toml",
    )
    initialize_tracked_git_repo(repo)


def state_for(root: Path) -> AoADecisionsMCPState:
    return AoADecisionsMCPState.discover(
        workspace_root=root,
        stack_root=STACK_ROOT,
        output_dir=root / "graph",
        include_stack_repo=False,
    )


def read_state_for(root: Path) -> AoADecisionsMCPState:
    return AoADecisionsMCPState.discover(
        workspace_root=root,
        stack_root=STACK_ROOT,
        output_dir=root / "graph",
        include_stack_repo=False,
        cache_write_allowed=False,
    )


def test_status_auto_refreshes_graph_cache(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)

    status = state.ensure_fresh()

    assert status["status"] == "refreshed"
    assert status["cache_status"] == "refreshed"
    assert status["freshness_scope"] == "local_workspace_filesystem"
    assert status["remote_freshness_checked"] is False
    assert status["source_posture_status"] == "aligned"
    assert status["source_warnings"] == []
    assert "repo_source_postures" not in status
    assert status["decision_count"] == 1
    assert (tmp_path / "graph" / "workspace_decision_graph.json").is_file()
    assert (tmp_path / "graph" / "nodes.jsonl").is_file()
    assert (tmp_path / "graph" / "edges.jsonl").is_file()


def test_read_contour_denies_missing_cache_without_creating_output(
    tmp_path: Path,
) -> None:
    seed_workspace(tmp_path)
    state = read_state_for(tmp_path)

    posture = state.cache_posture()

    assert posture["status"] == "missing"
    assert posture["cache_write_allowed"] is False
    assert not state.output_dir.exists()
    with pytest.raises(
        DecisionGraphCacheUnavailable, match="read contour cannot refresh"
    ):
        state.summary()
    assert not state.output_dir.exists()


def test_read_contour_denies_stale_cache_without_rewriting_it(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    writer = state_for(tmp_path)
    writer.ensure_fresh()
    graph_before = writer.graph_path.read_bytes()
    summary_before = writer.summary_path.read_bytes()
    write_decision(
        tmp_path / "repo-a", "AAA-D-0002", "Second Decision", "docs/other.md"
    )
    reader = read_state_for(tmp_path)

    assert reader.cache_posture()["status"] == "stale"
    with pytest.raises(DecisionGraphCacheUnavailable, match="cache is stale"):
        reader.packet(query="First")

    assert writer.graph_path.read_bytes() == graph_before
    assert writer.summary_path.read_bytes() == summary_before
    assert not (writer.output_dir / core.LOCK_NAME).exists()


def test_read_and_internal_effect_servers_have_disjoint_tools(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    read = build_server(
        workspace_root=tmp_path,
        stack_root=STACK_ROOT,
        output_dir=tmp_path / "graph",
        contour="read",
    )
    internal_effect = build_server(
        workspace_root=tmp_path,
        stack_root=STACK_ROOT,
        output_dir=tmp_path / "graph",
        contour="internal_effect",
    )

    read_tools = {tool.name: tool for tool in asyncio.run(read.list_tools())}
    effect_tools = {
        tool.name: tool for tool in asyncio.run(internal_effect.list_tools())
    }

    assert read._mcp_server.version == "0.2.0"
    assert internal_effect._mcp_server.version == "0.2.0"
    assert "aoa_decisions_refresh" not in read_tools
    assert (
        "force_refresh"
        not in read_tools["aoa_decisions_status"].inputSchema["properties"]
    )
    assert set(effect_tools) == {"aoa_decisions_status", "aoa_decisions_refresh"}
    for tool in read_tools.values():
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is False
    assert effect_tools["aoa_decisions_status"].annotations.readOnlyHint is True
    assert effect_tools["aoa_decisions_refresh"].annotations is None


def test_read_server_status_never_materializes_cache(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    output_dir = tmp_path / "graph"
    server = build_server(
        workspace_root=tmp_path,
        stack_root=STACK_ROOT,
        output_dir=output_dir,
        contour="read",
    )

    _, result = asyncio.run(server.call_tool("aoa_decisions_status", {}))

    assert result["status"] == "missing"
    assert result["cache_write_allowed"] is False
    assert not output_dir.exists()


def test_status_downgrades_when_local_tracking_ref_is_ahead_of_checkout(
    tmp_path: Path,
) -> None:
    seed_workspace(tmp_path)
    repo = tmp_path / "repo-a"
    state = state_for(tmp_path)
    first = state.ensure_fresh()

    git(repo, "switch", "-c", "origin-progress")
    (repo / "remote-only.txt").write_text("tracking progress\n", encoding="utf-8")
    git(repo, "add", "remote-only.txt")
    git(repo, "commit", "-m", "tracking progress")
    tracking_sha = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "main")
    git(repo, "update-ref", "refs/remotes/origin/main", tracking_sha)
    git(repo, "branch", "-D", "origin-progress")

    warning = state.ensure_fresh()
    repo_packet = state.repo("repo-a")
    issues_packet = state.issues(repo="repo-a")
    cached_warning = state.ensure_fresh()

    assert warning["status"] == "refreshed-with-source-warnings"
    assert warning["cache_status"] == "refreshed"
    assert warning["source_posture_status"] == "warnings"
    assert warning["local_tracking_lag_repo_count"] == 1
    assert warning["source_warning_repo_count"] == 1
    assert warning["source_warnings"] == [
        {
            "repo": "repo-a",
            "relation": "behind",
            "dirty": False,
            "ahead_count": 0,
            "behind_count": 1,
        }
    ]
    assert "repo_source_postures" not in warning
    assert warning["issue_count"] == 0
    assert warning["input_fingerprint"] != first["input_fingerprint"]
    assert repo_packet["source_posture"]["relation"] == "behind"
    assert repo_packet["source_posture"]["remote_freshness_checked"] is False
    assert issues_packet["issue_count"] == 0
    assert issues_packet["source_warning_repo_count"] == 1
    assert cached_warning["status"] == "fresh-with-source-warnings"
    assert cached_warning["cache_status"] == "fresh"


def test_status_rebuilds_when_decision_lane_changes(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)
    first = state.summary()
    write_decision(
        tmp_path / "repo-a", "AAA-D-0002", "Second Decision", "docs/other.md"
    )

    second = state.summary()

    assert first["decision_count"] == 1
    assert second["decision_count"] == 2
    assert first["input_fingerprint"] != second["input_fingerprint"]
    assert second["freshness"]["refreshed"] is True


def test_cached_status_keeps_structural_issues_visible(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    unknown = tmp_path / "repo-a" / "docs" / "decisions" / "entities" / "unknown.yaml"
    unknown.parent.mkdir(parents=True)
    unknown.write_text("schema: unknown\n", encoding="utf-8")
    state = state_for(tmp_path)

    refreshed = state.ensure_fresh()
    cached = state.ensure_fresh()

    assert refreshed["status"] == "refreshed-with-issues"
    assert refreshed["issue_count"] == 1
    assert cached["status"] == "fresh-with-issues"
    assert cached["cache_status"] == "fresh"
    assert cached["issue_count"] == 1


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
    assert (
        symmetry_packet["repos"][0]["symmetry_note"]
        == "compare coverage posture; do not force identical repo structure"
    )
    assert issues_packet["schema"] == "aoa_decisions_issues_packet_v1"
    assert issues_packet["issue_count"] == 0


def test_path_packets_include_route_anchor_impacts(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)

    changed_packet = state.changed_path("config/app.toml", repo="repo-a")
    packet = state.packet(path="config/app.toml", repo="repo-a")

    assert changed_packet["decision_count"] == 1
    assert changed_packet["decisions"][0]["label"] == "AAA-D-0001"
    assert any(
        surface.get("facet_key") == "Route anchors"
        for surface in changed_packet["surfaces"]
    )
    assert any(edge["type"] == "HAS_DECISION_FACET" for edge in changed_packet["edges"])
    assert packet["decision_count"] == 1
    assert packet["decisions"][0]["label"] == "AAA-D-0001"
    assert any(edge["type"] == "HAS_DECISION_FACET" for edge in packet["edges"])


def test_route_anchor_path_packets_respect_repo_scope(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    repo_b = tmp_path / "repo-b"
    (repo_b / ".git").mkdir(parents=True)
    (repo_b / "docs" / "decisions" / "indexes").mkdir(parents=True)
    (repo_b / "docs" / "decisions" / "indexes" / "README.md").write_text(
        "# Index\n", encoding="utf-8"
    )
    write_decision(
        repo_b,
        "BBB-D-0001",
        "Foreign Decision",
        "docs/foreign.md",
        route_anchor="config/foreign.toml",
    )
    state = state_for(tmp_path)

    changed_packet = state.changed_path("config/foreign.toml", repo="repo-a")
    packet = state.packet(path="config/foreign.toml", repo="repo-a")

    assert changed_packet["decision_count"] == 0
    assert changed_packet["surfaces"] == []
    assert changed_packet["edges"] == []
    assert packet["decision_count"] == 0
    assert packet["nodes"] == []
    assert packet["edges"] == []


def test_resources_and_server_build(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)

    summary = state.read_resource("aoa-decisions://summary")
    decision = state.read_resource("aoa-decisions://decision/AAA-D-0001")
    issues = state.read_resource("aoa-decisions://issues")

    assert summary["decision_count"] == 1
    assert decision["matches"][0]["label"] == "AAA-D-0001"
    assert issues["issue_count"] == 0
    assert (
        json.loads(state.render_resource("aoa-decisions://status"))["decision_count"]
        == 1
    )
    assert (
        build_server(
            workspace_root=tmp_path,
            stack_root=STACK_ROOT,
            output_dir=tmp_path / "graph",
        )
        is not None
    )


def test_exact_decision_view_preserves_owner_status_rationale_and_revision(
    tmp_path: Path,
) -> None:
    seed_workspace(tmp_path)
    state = state_for(tmp_path)
    state.ensure_fresh()

    packet = state.decision("AAA-D-0001")

    assert len(packet["decision_views"]) == 1
    view = packet["decision_views"][0]
    assert view["decision_id"] == "AAA-D-0001"
    assert view["repository_owner"] == "repo-a"
    assert view["status"] == "accepted"
    assert view["rationale_summary"] == "accepted"
    assert view["rationale_source_ref"].startswith(
        "repo://repo-a/docs/decisions/AAA-D-0001"
    )
    assert view["source_revision"].startswith("sha256:")
    assert view["repository_revision"] == git(
        tmp_path / "repo-a", "rev-parse", "HEAD"
    )
    assert view["source_posture"]["remote_freshness_checked"] is False
    assert view["predecessors"] == []
    assert view["successors"] == []
    assert view["superseded_by"] == []
    assert packet["claim_limits"]
