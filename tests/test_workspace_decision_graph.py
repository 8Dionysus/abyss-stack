from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_workspace_decision_graph as workspace_graph  # noqa: E402


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
    git(repo_root, "remote", "add", "origin", f"https://github.com/example/{repo_root.name}.git")
    git(repo_root, "add", ".")
    git(repo_root, "commit", "-m", "seed")
    git(repo_root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo_root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")


def test_default_local_stack_root_is_current_checkout() -> None:
    source = (SCRIPTS_DIR / "build_workspace_decision_graph.py").read_text(encoding="utf-8")

    assert workspace_graph.DEFAULT_LOCAL_STACK_ROOT == ROOT
    assert 'Path("/home/dionysus/src/abyss-stack")' not in source


def test_repo_source_posture_distinguishes_alignment_dirty_and_local_ahead(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    write_decision(repo, decision_id="AAA-D-0001", title="First")
    initialize_tracked_git_repo(repo)

    aligned = workspace_graph.collect_repo_source_posture(repo)

    assert aligned == {
        "repo": "repo",
        "head_sha": git(repo, "rev-parse", "HEAD"),
        "head_ref": "main",
        "local_tracking_ref": "origin/main",
        "local_tracking_sha": git(repo, "rev-parse", "refs/remotes/origin/main"),
        "ahead_count": 0,
        "behind_count": 0,
        "relation": "aligned",
        "dirty": False,
        "comparison_basis": "local_remote_tracking_ref_without_fetch",
        "remote_freshness_checked": False,
    }

    (repo / "scratch.txt").write_text("dirty\n", encoding="utf-8")
    dirty = workspace_graph.collect_repo_source_posture(repo)
    assert dirty["relation"] == "aligned"
    assert dirty["dirty"] is True

    git(repo, "add", "scratch.txt")
    git(repo, "commit", "-m", "local work")
    ahead = workspace_graph.collect_repo_source_posture(repo)
    assert ahead["relation"] == "ahead"
    assert ahead["ahead_count"] == 1
    assert ahead["behind_count"] == 0
    assert ahead["dirty"] is False


def test_workspace_fingerprint_and_graph_include_local_source_posture(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    write_decision(repo, decision_id="AAA-D-0001", title="First")
    initialize_tracked_git_repo(repo)
    records, surfaces, issues = workspace_graph.collect_workspace_decision_inputs([repo])
    first_postures = workspace_graph.collect_repo_source_postures([repo])
    first_fingerprint = workspace_graph.workspace_input_fingerprint([repo], first_postures)
    first_graph = workspace_graph.build_workspace_graph(
        records,
        surfaces=surfaces,
        input_fingerprint=first_fingerprint,
        repo_source_postures=first_postures,
    )

    assert issues == []
    assert first_graph["freshness_scope"] == "local_workspace_filesystem"
    assert first_graph["remote_freshness_checked"] is False
    assert first_graph["repo_source_posture_counts"] == {"aligned": 1}
    assert first_graph["source_warning_repo_count"] == 0
    assert first_graph["local_tracking_lag_repo_count"] == 0
    assert first_graph["local_unpublished_repo_count"] == 0
    assert first_graph["dirty_repo_count"] == 0
    assert first_graph["unknown_source_posture_count"] == 0

    (repo / "runtime-note.txt").write_text("local only\n", encoding="utf-8")
    git(repo, "add", "runtime-note.txt")
    git(repo, "commit", "-m", "advance local head")
    second_postures = workspace_graph.collect_repo_source_postures([repo])
    second_fingerprint = workspace_graph.workspace_input_fingerprint([repo], second_postures)
    second_graph = workspace_graph.build_workspace_graph(
        records,
        surfaces=surfaces,
        input_fingerprint=second_fingerprint,
        repo_source_postures=second_postures,
    )
    summary = workspace_graph.graph_summary(second_graph, issues)

    assert second_fingerprint != first_fingerprint
    assert second_graph["repo_source_postures"][0]["relation"] == "ahead"
    assert summary["source_warning_repo_count"] == 1
    assert summary["local_unpublished_repo_count"] == 1


def test_repo_identity_uses_origin_name_in_arbitrarily_named_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "abyss-stack-feature-worktree"
    repo.mkdir()
    write_decision(repo, decision_id="ABYSS-STACK-D-0001", title="First")
    initialize_tracked_git_repo(repo)
    git(repo, "remote", "set-url", "origin", "git@github.com:AbyssBootstrap/abyss-stack.git")

    records, issues = workspace_graph.collect_workspace_decisions([repo])
    posture = workspace_graph.collect_repo_source_posture(repo)

    assert issues == []
    assert workspace_graph.repo_identity(repo) == "abyss-stack"
    assert records[0].repo == "abyss-stack"
    assert posture["repo"] == "abyss-stack"


def test_explicit_repo_root_wins_duplicate_origin_identity(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    canonical = workspace / "abyss-stack"
    explicit = tmp_path / "abyss-stack-feature-worktree"
    for repo, decision_id in (
        (canonical, "ABYSS-STACK-D-0001"),
        (explicit, "ABYSS-STACK-D-0002"),
    ):
        repo.mkdir(parents=True)
        write_decision(repo, decision_id=decision_id, title=decision_id)
        initialize_tracked_git_repo(repo)
        git(repo, "remote", "set-url", "origin", "git@github.com:AbyssBootstrap/abyss-stack.git")

    repos = workspace_graph.discover_decision_repos(
        workspace_root=workspace,
        extra_repo_roots=[explicit],
    )

    assert repos == [explicit.resolve()]


def write_decision(
    repo_root: Path,
    *,
    decision_id: str,
    title: str,
    status: str = "accepted",
    date: str = "2026-06-04",
    owner_surface: str = "docs/decisions/",
    facets: dict[str, str] | None = None,
    superseded_by: str | None = None,
) -> None:
    facets = facets or {"Surface classes": "docs route", "Guard families": "decision graph"}
    top_lines = [
        f"# {title}",
        "",
        f"- Decision ID: {decision_id}",
        f"- Status: {status}",
    ]
    if superseded_by is not None:
        top_lines.append(f"- Superseded by: `{superseded_by}.md`")
    top_lines.extend(
        [
            f"- Date: {date}",
            f"- Owner surface: `{owner_surface}`",
            "",
            "## Index Metadata",
            "",
            f"- Original date: {date}",
        ]
    )
    top_lines.extend(f"- {key}: {value}" for key, value in facets.items())
    top_lines.extend(
        [
            "- Posture: test graph route",
            "",
            "## Context",
            "",
            "A decision exists.",
            "",
            "## Source surfaces",
            "",
            "- `docs/decisions/README.md`",
            "- `scripts/generate_decision_indexes.py`",
        ]
    )
    path = repo_root / "docs" / "decisions" / f"{decision_id.lower()}-test.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(top_lines) + "\n", encoding="utf-8")


def write_index_metadata_decision(
    repo_root: Path,
    *,
    decision_id: str,
    title: str,
    status_line: str = "",
    status_section: str = "",
    posture: str = "accepted",
    date: str = "2026-06-04",
) -> None:
    lines = [f"# {title}", ""]
    if status_line:
        lines.extend([status_line, ""])
    lines.extend(
        [
            "## Index Metadata",
            "",
            f"- Decision ID: {decision_id}",
            f"- Original date: {date}",
            "- Surface classes: docs route",
            "- Guard families: decision graph",
            f"- Posture: {posture}",
            "",
        ]
    )
    if status_section:
        lines.extend(["## Status", "", status_section, ""])
    lines.extend(
        [
            "## Context",
            "",
            "A decision exists.",
        ]
    )
    path = repo_root / "docs" / "decisions" / f"{decision_id}-index-only.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_workspace_decision_graph_discovers_repos_facets_and_edges(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    for repo in (repo_a, repo_b):
        (repo / ".git").mkdir(parents=True)
        (repo / "docs" / "decisions" / "indexes").mkdir(parents=True)
        (repo / "docs" / "decisions" / "README.md").write_text("# Decisions\n", encoding="utf-8")
        (repo / "docs" / "decisions" / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
        (repo / "docs" / "decisions" / "TEMPLATE.md").write_text("# Template\n", encoding="utf-8")
        (repo / "docs" / "decisions" / "indexes" / "README.md").write_text("# Index\n", encoding="utf-8")

    write_decision(
        repo_a,
        decision_id="AAA-D-0001",
        title="First Repo A",
        status="superseded",
        facets={"Repo lane": "alpha", "Guard families": "decision graph"},
        superseded_by="AAA-D-0002",
    )
    write_decision(
        repo_a,
        decision_id="AAA-D-0002",
        title="Second Repo A",
        facets={"Repo lane": "alpha", "Guard families": "decision graph"},
    )
    write_decision(
        repo_b,
        decision_id="BBB-D-0001",
        title="First Repo B",
        facets={"Repo lane": "beta", "Owner facet": "operator"},
    )

    repos = workspace_graph.discover_decision_repos(workspace_root=tmp_path)
    records, surfaces, issues = workspace_graph.collect_workspace_decision_inputs(repos)
    graph = workspace_graph.build_workspace_graph(records, surfaces=surfaces)

    assert issues == []
    assert graph["repo_count"] == 2
    assert graph["decision_count"] == 3
    assert graph["decision_surface_count"] == 11
    node_ids = {node["id"] for node in graph["nodes"]}
    edge_keys = {(edge["source"], edge["target"], edge["type"]) for edge in graph["edges"]}
    assert "repo:repo-a" in node_ids
    assert "decision:repo-a:AAA-D-0001" in node_ids
    assert "decision:repo-b:BBB-D-0001" in node_ids
    assert "decision_lane_doc:repo-a:docs/decisions/README.md" in node_ids
    assert "decision_lane_doc:repo-a:docs/decisions/AGENTS.md" in node_ids
    assert "decision_lane_doc:repo-a:docs/decisions/TEMPLATE.md" in node_ids
    assert "decision_index:repo-a:docs/decisions/indexes/README.md" in node_ids
    assert "decision_facet:Repo%20lane:alpha" in node_ids
    assert "source_surface:repo-a:docs/decisions/README.md" in node_ids
    assert (
        "decision_lane:repo-a",
        "decision_lane_doc:repo-a:docs/decisions/README.md",
        "HAS_DECISION_LANE_DOC",
    ) in edge_keys
    assert (
        "decision:repo-a:AAA-D-0001",
        "decision:repo-a:AAA-D-0002",
        "SUPERSEDED_BY",
    ) in edge_keys
    assert (
        "decision:repo-a:AAA-D-0001",
        "source_surface:repo-a:docs/decisions/README.md",
        "CITES_SOURCE_SURFACE",
    ) in edge_keys


def test_workspace_decision_graph_accepts_index_metadata_only_records(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    write_index_metadata_decision(repo, decision_id="IDX-D-0001", title="Index Metadata Only")

    records, issues = workspace_graph.collect_workspace_decisions([repo])
    graph = workspace_graph.build_workspace_graph(records)

    assert issues == []
    assert records[0].decision_id == "IDX-D-0001"
    assert records[0].status == "accepted"
    assert records[0].date == "2026-06-04"
    assert records[0].owner_surfaces == ("docs/decisions/",)
    node_ids = {node["id"] for node in graph["nodes"]}
    assert "decision:repo:IDX-D-0001" in node_ids
    assert "decision_facet:Decision%20ID:IDX-D-0001" not in node_ids


def test_workspace_decision_graph_flags_unknown_decision_surfaces(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    write_decision(repo, decision_id="AAA-D-0001", title="First")
    unknown = repo / "docs" / "decisions" / "entities" / "new-kind.yaml"
    unknown.parent.mkdir(parents=True)
    unknown.write_text("schema: future_surface_v1\n", encoding="utf-8")

    records, surfaces, issues = workspace_graph.collect_workspace_decision_inputs([repo])
    graph = workspace_graph.build_workspace_graph(records, surfaces=surfaces)
    summary = workspace_graph.graph_summary(graph, issues)

    assert records[0].decision_id == "AAA-D-0001"
    assert summary["issue_count"] == 1
    assert issues[0]["path"] == "docs/decisions/entities/new-kind.yaml"
    assert "unmodeled decision surface" in issues[0]["error"]


def test_workspace_decision_graph_keeps_surface_only_repos_visible(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    decisions = repo / "docs" / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "README.md").write_text("# Decisions\n", encoding="utf-8")

    records, surfaces, issues = workspace_graph.collect_workspace_decision_inputs([repo])
    graph = workspace_graph.build_workspace_graph(records, surfaces=surfaces)

    assert issues == []
    assert records == []
    assert graph["repo_count"] == 1
    assert graph["decision_count"] == 0
    assert graph["repo_decision_counts"] == {"repo": 0}
    node_ids = {node["id"] for node in graph["nodes"]}
    assert "decision_lane:repo" in node_ids
    assert "decision_lane_doc:repo:docs/decisions/README.md" in node_ids


def test_workspace_decision_graph_accepts_status_variants_and_text_supersession(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    write_index_metadata_decision(
        repo,
        decision_id="IDX-D-0001",
        title="Plain Status",
        status_line="Status: accepted for archive placement; active placement superseded by `IDX-D-0002.md`",
    )
    write_index_metadata_decision(
        repo,
        decision_id="IDX-D-0002",
        title="Section Status",
        status_section="Accepted.",
        posture="proposed rationale",
    )

    records, issues = workspace_graph.collect_workspace_decisions([repo])
    graph = workspace_graph.build_workspace_graph(records)

    assert issues == []
    assert {record.decision_id: record.status for record in records} == {
        "IDX-D-0001": "accepted",
        "IDX-D-0002": "accepted",
    }
    edge_keys = {(edge["source"], edge["target"], edge["type"]) for edge in graph["edges"]}
    assert (
        "decision:repo:IDX-D-0001",
        "decision:repo:IDX-D-0002",
        "SUPERSEDED_BY",
    ) in edge_keys


def test_workspace_decision_graph_writes_json_and_jsonl_outputs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    write_decision(repo, decision_id="AAA-D-0001", title="First")
    records, issues = workspace_graph.collect_workspace_decisions([repo])
    graph = workspace_graph.build_workspace_graph(records)
    output_dir = tmp_path / "out"

    workspace_graph.write_graph_outputs(graph, issues, output_dir)

    assert workspace_graph.output_matches(graph, issues, output_dir)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["repo_count"] == 1
    assert summary["decision_count"] == 1
    assert (output_dir / "nodes.jsonl").read_text(encoding="utf-8").strip()
    assert (output_dir / "edges.jsonl").read_text(encoding="utf-8").strip()
