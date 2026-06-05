from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
TESTS_DIR = ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import build_workspace_decision_graph as workspace_graph  # noqa: E402
import validate_workspace_decision_graph as graph_contract  # noqa: E402
from test_workspace_decision_graph import write_decision  # noqa: E402


def seed_graph(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo-a"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "decisions" / "README.md").parent.mkdir(parents=True)
    (repo / "docs" / "decisions" / "README.md").write_text("# Decisions\n", encoding="utf-8")
    (repo / "docs" / "decisions" / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    (repo / "docs" / "decisions" / "TEMPLATE.md").write_text("# Template\n", encoding="utf-8")
    write_decision(repo, decision_id="AAA-D-0001", title="First")
    output_dir = tmp_path / "graph"
    records, surfaces, issues = workspace_graph.collect_workspace_decision_inputs([repo])
    graph = workspace_graph.build_workspace_graph(
        records,
        surfaces=surfaces,
        input_fingerprint=workspace_graph.workspace_input_fingerprint([repo]),
    )
    workspace_graph.write_graph_outputs(graph, issues, output_dir)
    return repo, output_dir


def copy_schemas(tmp_path: Path) -> Path:
    repo_root = tmp_path / "stack"
    shutil.copytree(ROOT / "schemas", repo_root / "schemas")
    return repo_root


def test_workspace_graph_contract_validator_accepts_fresh_cache(tmp_path: Path) -> None:
    repo, output_dir = seed_graph(tmp_path)
    repo_root = copy_schemas(tmp_path)

    issues = graph_contract.validate(
        repo_root=repo_root,
        workspace_root=tmp_path,
        output_dir=output_dir,
        include_stack_repo=False,
    )

    assert issues == []


def test_workspace_graph_contract_validator_flags_jsonl_drift(tmp_path: Path) -> None:
    repo, output_dir = seed_graph(tmp_path)
    repo_root = copy_schemas(tmp_path)
    (output_dir / "nodes.jsonl").write_text("", encoding="utf-8")

    issues = graph_contract.validate(
        repo_root=repo_root,
        workspace_root=tmp_path,
        output_dir=output_dir,
        include_stack_repo=False,
    )

    assert (output_dir / "nodes.jsonl").as_posix() in {location for location, _ in issues}


def test_workspace_graph_contract_validator_runs_json_schema(tmp_path: Path) -> None:
    repo, output_dir = seed_graph(tmp_path)
    repo_root = copy_schemas(tmp_path)
    graph_path = output_dir / "workspace_decision_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    del graph["authority_note"]
    graph_path.write_text(json.dumps(graph, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    issues = graph_contract.validate(
        repo_root=repo_root,
        workspace_root=tmp_path,
        output_dir=output_dir,
        include_stack_repo=False,
    )

    assert any("schema validation failed" in message and "authority_note" in message for _, message in issues)


def test_workspace_graph_contract_validator_flags_unknown_node_type(tmp_path: Path) -> None:
    repo, output_dir = seed_graph(tmp_path)
    repo_root = copy_schemas(tmp_path)
    graph_path = output_dir / "workspace_decision_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["nodes"][0]["type"] = "future_node"
    graph["node_type_counts"] = {"future_node": 1}
    graph_path.write_text(json.dumps(graph, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    issues = graph_contract.validate(
        repo_root=repo_root,
        workspace_root=tmp_path,
        output_dir=output_dir,
        include_stack_repo=False,
    )

    assert any("unknown node types: future_node" in message for _, message in issues)
