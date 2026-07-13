#!/usr/bin/env python3
"""Validate the workspace decision graph cache and schema contract."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

import build_workspace_decision_graph as builder


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = Path("schemas")
GRAPH_SCHEMA_PATH = SCHEMA_DIR / "workspace_decision_graph.schema.json"
SUMMARY_SCHEMA_PATH = SCHEMA_DIR / "workspace_decision_graph_summary.schema.json"
NODE_SCHEMA_PATH = SCHEMA_DIR / "workspace_decision_graph_node.schema.json"
EDGE_SCHEMA_PATH = SCHEMA_DIR / "workspace_decision_graph_edge.schema.json"
SOURCE_POSTURE_SCHEMA_PATH = SCHEMA_DIR / "workspace_decision_repo_source_posture.schema.json"


def _load_json(path: Path, issues: list[tuple[str, str]]) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append((path.as_posix(), f"invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"))
        return None


def _load_jsonl(path: Path, issues: list[tuple[str, str]]) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append((path.as_posix(), f"invalid JSONL at line {line_number}: {exc.msg}"))
            return None
        if not isinstance(row, dict):
            issues.append((path.as_posix(), f"line {line_number} is not a JSON object"))
            return None
        rows.append(row)
    return rows


def _schema_enum(schema: dict[str, Any], property_name: str) -> list[str]:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return []
    property_schema = properties.get(property_name, {})
    if not isinstance(property_schema, dict):
        return []
    values = property_schema.get("enum", [])
    return list(values) if isinstance(values, list) else []


def _type_counts(items: Sequence[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get("type", "")) for item in items).items()))


def _schema_registry(schemas: dict[Path, Any]) -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    for path, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            resources.append((schema_id, Resource.from_contents(schema, default_specification=DRAFT202012)))
    return Registry().with_resources(resources)


def _validate_schema(
    *,
    payload: Any,
    schema: dict[str, Any],
    schemas: dict[Path, Any],
    location: Path,
    issues: list[tuple[str, str]],
) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        issues.append((location.as_posix(), f"invalid JSON schema: {exc.message}"))
        return

    validator = Draft202012Validator(schema, registry=_schema_registry(schemas))
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        path = "/".join(str(part) for part in error.absolute_path) or "$"
        issues.append((location.as_posix(), f"schema validation failed at {path}: {error.message}"))


def validate(
    *,
    repo_root: Path = REPO_ROOT,
    workspace_root: Path = builder.DEFAULT_WORKSPACE_ROOT,
    output_dir: Path = builder.DEFAULT_OUTPUT_DIR,
    include_stack_repo: bool = True,
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    repo_root = repo_root.resolve()
    output = output_dir if output_dir.is_absolute() else repo_root / output_dir

    graph_schema = _load_json(repo_root / GRAPH_SCHEMA_PATH, issues)
    summary_schema = _load_json(repo_root / SUMMARY_SCHEMA_PATH, issues)
    node_schema = _load_json(repo_root / NODE_SCHEMA_PATH, issues)
    edge_schema = _load_json(repo_root / EDGE_SCHEMA_PATH, issues)
    source_posture_schema = _load_json(repo_root / SOURCE_POSTURE_SCHEMA_PATH, issues)
    schemas = {
        GRAPH_SCHEMA_PATH: graph_schema,
        SUMMARY_SCHEMA_PATH: summary_schema,
        NODE_SCHEMA_PATH: node_schema,
        EDGE_SCHEMA_PATH: edge_schema,
        SOURCE_POSTURE_SCHEMA_PATH: source_posture_schema,
    }
    for path, schema in schemas.items():
        if not isinstance(schema, dict):
            issues.append((path.as_posix(), "schema file is missing or invalid JSON object"))

    if isinstance(graph_schema, dict):
        schema_const = graph_schema.get("properties", {}).get("schema", {}).get("const")
        if schema_const != builder.GRAPH_SCHEMA:
            issues.append((GRAPH_SCHEMA_PATH.as_posix(), f"schema const must be {builder.GRAPH_SCHEMA}"))
    if isinstance(summary_schema, dict):
        schema_const = summary_schema.get("properties", {}).get("schema", {}).get("const")
        if schema_const != builder.GRAPH_SUMMARY_SCHEMA:
            issues.append((SUMMARY_SCHEMA_PATH.as_posix(), f"schema const must be {builder.GRAPH_SUMMARY_SCHEMA}"))
    if isinstance(node_schema, dict) and tuple(_schema_enum(node_schema, "type")) != builder.NODE_TYPES:
        issues.append((NODE_SCHEMA_PATH.as_posix(), "node type enum must match build_workspace_decision_graph.NODE_TYPES"))
    if isinstance(edge_schema, dict) and tuple(_schema_enum(edge_schema, "type")) != builder.EDGE_TYPES:
        issues.append((EDGE_SCHEMA_PATH.as_posix(), "edge type enum must match build_workspace_decision_graph.EDGE_TYPES"))

    graph_path = output / "workspace_decision_graph.json"
    summary_path = output / "summary.json"
    nodes_path = output / "nodes.jsonl"
    edges_path = output / "edges.jsonl"
    graph = _load_json(graph_path, issues)
    summary = _load_json(summary_path, issues)
    nodes_jsonl = _load_jsonl(nodes_path, issues)
    edges_jsonl = _load_jsonl(edges_path, issues)

    if not isinstance(graph, dict):
        issues.append((graph_path.as_posix(), "workspace decision graph JSON is missing or invalid"))
    if not isinstance(summary, dict):
        issues.append((summary_path.as_posix(), "workspace decision graph summary is missing or invalid"))
    if nodes_jsonl is None:
        issues.append((nodes_path.as_posix(), "workspace decision graph nodes JSONL is missing"))
    if edges_jsonl is None:
        issues.append((edges_path.as_posix(), "workspace decision graph edges JSONL is missing"))
    if issues:
        return issues

    assert isinstance(graph, dict)
    assert isinstance(summary, dict)
    assert nodes_jsonl is not None
    assert edges_jsonl is not None

    if isinstance(graph_schema, dict):
        _validate_schema(payload=graph, schema=graph_schema, schemas=schemas, location=graph_path, issues=issues)
    if isinstance(summary_schema, dict):
        _validate_schema(payload=summary, schema=summary_schema, schemas=schemas, location=summary_path, issues=issues)
    if isinstance(node_schema, dict):
        for index, node in enumerate(nodes_jsonl):
            _validate_schema(payload=node, schema=node_schema, schemas=schemas, location=nodes_path, issues=issues)
    if isinstance(edge_schema, dict):
        for index, edge in enumerate(edges_jsonl):
            _validate_schema(payload=edge, schema=edge_schema, schemas=schemas, location=edges_path, issues=issues)

    if graph.get("schema") != builder.GRAPH_SCHEMA:
        issues.append((graph_path.as_posix(), f"schema must be {builder.GRAPH_SCHEMA}"))
    if summary.get("schema") != builder.GRAPH_SUMMARY_SCHEMA:
        issues.append((summary_path.as_posix(), f"schema must be {builder.GRAPH_SUMMARY_SCHEMA}"))
    if graph.get("nodes") != nodes_jsonl:
        issues.append((nodes_path.as_posix(), "nodes JSONL must match workspace_decision_graph.json nodes"))
    if graph.get("edges") != edges_jsonl:
        issues.append((edges_path.as_posix(), "edges JSONL must match workspace_decision_graph.json edges"))

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
        issues.append((graph_path.as_posix(), "nodes must be a list of objects"))
        nodes = []
    if not isinstance(edges, list) or not all(isinstance(edge, dict) for edge in edges):
        issues.append((graph_path.as_posix(), "edges must be a list of objects"))
        edges = []

    node_type_counts = _type_counts(nodes)
    edge_type_counts = _type_counts(edges)
    unknown_node_types = sorted(set(node_type_counts) - set(builder.NODE_TYPES))
    unknown_edge_types = sorted(set(edge_type_counts) - set(builder.EDGE_TYPES))
    if unknown_node_types:
        issues.append((graph_path.as_posix(), "unknown node types: " + ", ".join(unknown_node_types)))
    if unknown_edge_types:
        issues.append((graph_path.as_posix(), "unknown edge types: " + ", ".join(unknown_edge_types)))
    if int(graph.get("node_count") or -1) != len(nodes):
        issues.append((graph_path.as_posix(), "node_count must match nodes length"))
    if int(graph.get("edge_count") or -1) != len(edges):
        issues.append((graph_path.as_posix(), "edge_count must match edges length"))
    if graph.get("node_type_counts") != node_type_counts:
        issues.append((graph_path.as_posix(), "node_type_counts must match nodes"))
    if graph.get("edge_type_counts") != edge_type_counts:
        issues.append((graph_path.as_posix(), "edge_type_counts must match edges"))

    repo_source_postures = graph.get("repo_source_postures", [])
    if isinstance(repo_source_postures, list) and all(isinstance(item, dict) for item in repo_source_postures):
        expected_posture_summary = builder.summarize_repo_source_postures(repo_source_postures)
        if any(graph.get(key) != value for key, value in expected_posture_summary.items()):
            issues.append((graph_path.as_posix(), "source posture summary must match repo_source_postures"))
        posture_repos = [str(item.get("repo", "")) for item in repo_source_postures]
        graph_repos = sorted(
            (str(repo) for repo in graph.get("repo_decision_counts", {})),
            key=str.lower,
        )
        if posture_repos != graph_repos:
            issues.append((graph_path.as_posix(), "repo_source_postures must cover each graph repo exactly once"))

    for key in (
        "freshness_scope",
        "remote_freshness_checked",
        "source_posture_note",
        "input_fingerprint",
        "repo_count",
        "decision_count",
        "decision_surface_count",
        "node_count",
        "edge_count",
        "repo_decision_counts",
        "node_type_counts",
        "edge_type_counts",
        "surface_kind_counts",
        "repo_source_postures",
        "repo_source_posture_counts",
        "source_warning_repo_count",
        "local_tracking_lag_repo_count",
        "local_unpublished_repo_count",
        "dirty_repo_count",
        "unknown_source_posture_count",
    ):
        if summary.get(key) != graph.get(key):
            issues.append((summary_path.as_posix(), f"{key} must match workspace_decision_graph.json"))
    if int(summary.get("issue_count") or 0) != len(summary.get("issues", [])):
        issues.append((summary_path.as_posix(), "issue_count must match issues length"))

    repo_roots = builder.discover_decision_repos(
        workspace_root=workspace_root,
        extra_repo_roots=[builder.DEFAULT_LOCAL_STACK_ROOT] if include_stack_repo and builder.DEFAULT_LOCAL_STACK_ROOT.is_dir() else [],
    )
    records, surfaces, source_issues = builder.collect_workspace_decision_inputs(repo_roots)
    repo_source_postures = builder.collect_repo_source_postures(repo_roots)
    expected_graph = builder.build_workspace_graph(
        records,
        surfaces=surfaces,
        input_fingerprint=builder.workspace_input_fingerprint(repo_roots, repo_source_postures),
        repo_source_postures=repo_source_postures,
    )
    if not builder.output_matches(expected_graph, source_issues, output):
        issues.append((output.as_posix(), "workspace decision graph cache is stale; run scripts/build_workspace_decision_graph.py --write"))

    return issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=builder.DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=builder.DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-stack-repo", action="store_true", help="do not include the local abyss-stack checkout as an extra repo")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    issues = validate(
        workspace_root=args.workspace_root,
        output_dir=args.output_dir,
        include_stack_repo=not args.no_stack_repo,
    )
    if args.json:
        print(json.dumps({"ok": not issues, "issue_count": len(issues), "issues": issues}, ensure_ascii=True, sort_keys=True))
    elif issues:
        for location, message in issues:
            print(f"- {location}: {message}")
    else:
        print("[ok] workspace decision graph contract validated")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
