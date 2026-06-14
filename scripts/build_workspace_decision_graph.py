#!/usr/bin/env python3
"""Build a workspace-wide decision graph from repo-local docs/decisions lanes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import quote


DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")
DEFAULT_LOCAL_STACK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("Logs/decision-graph/latest")
GRAPH_SCHEMA = "abyss_workspace_decision_graph_v1"
GRAPH_SUMMARY_SCHEMA = "abyss_workspace_decision_graph_summary_v1"
EXEMPT_DECISION_FILES = {"AGENTS.md", "README.md", "TEMPLATE.md"}
FINGERPRINT_EXCLUDED_DIRS = {"generated"}
LANE_DOCUMENT_SURFACE_KINDS = {
    "AGENTS.md": "lane_agents",
    "README.md": "lane_readme",
    "TEMPLATE.md": "decision_template",
}
NODE_TYPES = (
    "date",
    "decision",
    "decision_facet",
    "decision_index",
    "decision_lane",
    "decision_lane_doc",
    "owner_surface",
    "repo",
    "source_surface",
    "status",
)
EDGE_TYPES = (
    "CITES_SOURCE_SURFACE",
    "CONTAINS_DECISION",
    "DATED",
    "HAS_DECISION_FACET",
    "HAS_DECISION_INDEX",
    "HAS_DECISION_LANE",
    "HAS_DECISION_LANE_DOC",
    "HAS_STATUS",
    "NEXT_DECISION_IN_REPO",
    "OWNED_BY_SURFACE",
    "SUPERSEDED_BY",
)
SURFACE_KINDS = ("decision_index", "decision_record", "decision_template", "lane_agents", "lane_readme")
METADATA_LINE_RE = re.compile(r"^(?:-\s*)?(?P<key>[A-Za-z][A-Za-z0-9 _-]*):\s*(?P<value>.*)$", re.MULTILINE)
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
DECISION_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*-D-\d{4}")
DATE_VALUE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
STATUS_TOKEN_RE = re.compile(r"\b(accepted|proposed|superseded|amended|deprecated|draft)\b")
SECTION_HEADING_RE = re.compile(r"^##\s+(?P<heading>.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class WorkspaceDecisionRecord:
    repo: str
    repo_root: Path
    decision_id: str
    title: str
    status: str
    date: str
    path: Path
    owner_surfaces: tuple[str, ...]
    metadata_facets: tuple[tuple[str, tuple[str, ...]], ...]
    source_surfaces: tuple[str, ...]
    superseded_by: tuple[str, ...]
    source_sha256: str

    @property
    def repo_path(self) -> str:
        return self.path.as_posix()


@dataclass(frozen=True)
class WorkspaceDecisionSurface:
    repo: str
    repo_root: Path
    path: Path
    surface_kind: str
    node_type: str
    edge_type: str
    source_sha256: str

    @property
    def repo_path(self) -> str:
        return self.path.as_posix()


def _quote(value: str) -> str:
    return quote(value, safe="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-/")


def _node_id(kind: str, *parts: str) -> str:
    return ":".join((kind, *(_quote(part) for part in parts)))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint_files(repo_root: Path) -> tuple[Path, ...]:
    decisions_root = repo_root / "docs" / "decisions"
    if not decisions_root.is_dir():
        return ()
    files: list[Path] = []
    for path in sorted(decisions_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(decisions_root)
        except ValueError:
            continue
        if any(part in FINGERPRINT_EXCLUDED_DIRS for part in relative.parts):
            continue
        files.append(path)
    return tuple(files)


def workspace_input_fingerprint(repo_roots: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for repo_root in sorted((path.resolve() for path in repo_roots), key=lambda path: path.name.lower()):
        digest.update(f"repo:{repo_root.name}\n".encode("utf-8"))
        for path in _fingerprint_files(repo_root):
            relative = path.relative_to(repo_root).as_posix()
            digest.update(f"path:{relative}\nsha256:{_sha256(path)}\n".encode("utf-8"))
    return digest.hexdigest()


def _split_inline_code_or_value(value: str) -> tuple[str, ...]:
    coded_values = tuple(item.strip() for item in INLINE_CODE_RE.findall(value) if item.strip())
    if coded_values:
        return coded_values
    value = value.strip()
    if not value or value.lower() in {"none", "n/a"}:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_title(text: str, *, path: Path) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    raise ValueError(f"{path.as_posix()} is missing a level-one title")


def _parse_top_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    top_section = text.split("\n## Index Metadata", 1)[0]
    for match in METADATA_LINE_RE.finditer(top_section):
        metadata[match.group("key").strip().lower()] = match.group("value").strip()
    return metadata


def _parse_index_metadata(text: str) -> dict[str, str]:
    marker = "\n## Index Metadata\n"
    if marker not in text:
        return {}
    section = text.split(marker, 1)[1]
    next_heading = section.find("\n## ")
    if next_heading != -1:
        section = section[:next_heading]

    metadata: dict[str, str] = {}
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _section_text(text: str, heading: str) -> str:
    heading_match: re.Match[str] | None = None
    for match in SECTION_HEADING_RE.finditer(text):
        if match.group("heading").strip().lower() == heading.lower():
            heading_match = match
            break
    if heading_match is None:
        return ""

    section = text[heading_match.end() :]
    next_heading = SECTION_HEADING_RE.search(section)
    if next_heading is not None:
        section = section[: next_heading.start()]
    return section


def _parse_bullet_section(text: str, heading: str) -> tuple[str, ...]:
    section = _section_text(text, heading)
    if not section:
        return ()

    values: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        values.extend(_split_inline_code_or_value(line[2:].strip()))
    return tuple(dict.fromkeys(value for value in values if value))


def _parse_superseded_by(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for line in text.splitlines():
        if "superseded by" not in line.lower():
            continue
        tokens.extend(token.upper() for token in DECISION_TOKEN_RE.findall(line))
    return tuple(dict.fromkeys(tokens))


def _facet_pairs(index_metadata: dict[str, str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    structural_keys = {
        "date",
        "decision id",
        "original date",
        "owner surface",
        "owner surfaces",
        "status",
        "superseded by",
    }
    pairs: list[tuple[str, tuple[str, ...]]] = []
    for key, value in index_metadata.items():
        if key.lower() in structural_keys:
            continue
        values = _split_inline_code_or_value(value)
        if values:
            pairs.append((key, values))
    return tuple(pairs)


def _metadata_get(metadata: dict[str, str], key: str) -> str:
    wanted = key.lower()
    for metadata_key, value in metadata.items():
        if metadata_key.lower() == wanted:
            return value
    return ""


def _decision_id_from_value(value: str) -> str:
    match = DECISION_TOKEN_RE.search(value)
    return match.group(0).upper() if match is not None else ""


def _decision_id_from_path(path: Path) -> str:
    return _decision_id_from_value(path.name)


def _derive_decision_id(path: Path, top_metadata: dict[str, str], index_metadata: dict[str, str]) -> str:
    return (
        _decision_id_from_value(top_metadata.get("decision id", ""))
        or _decision_id_from_value(_metadata_get(index_metadata, "Decision ID"))
        or _decision_id_from_path(path)
    )


def _clean_status(value: str) -> str:
    value = value.strip().strip("`").strip().strip(".").lower()
    if not value:
        return ""
    match = STATUS_TOKEN_RE.search(value)
    if match is not None:
        return match.group(1)
    return re.sub(r"[^a-z0-9._-]+", "-", value).strip("-")


def _status_from_section(text: str) -> str:
    for raw_line in _section_text(text, "Status").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        return line
    return ""


def _derive_status(text: str, top_metadata: dict[str, str], index_metadata: dict[str, str]) -> str:
    candidates = (
        top_metadata.get("status", ""),
        _metadata_get(index_metadata, "Status"),
        _status_from_section(text),
        top_metadata.get("posture", ""),
        _metadata_get(index_metadata, "Posture"),
    )
    for candidate in candidates:
        status = _clean_status(candidate)
        if status:
            return status
    return "unknown"


def _clean_date(value: str) -> str:
    match = DATE_VALUE_RE.search(value)
    if match is not None:
        return match.group(0)
    return value.strip()


def _derive_date(top_metadata: dict[str, str], index_metadata: dict[str, str]) -> str:
    candidates = (
        _metadata_get(index_metadata, "Original date"),
        top_metadata.get("date", ""),
        _metadata_get(index_metadata, "Date"),
    )
    for candidate in candidates:
        date = _clean_date(candidate)
        if date:
            return date
    return "unknown"


def _derive_owner_surfaces(top_metadata: dict[str, str], index_metadata: dict[str, str]) -> tuple[str, ...]:
    candidates = (
        top_metadata.get("owner surface", ""),
        top_metadata.get("owner surfaces", ""),
        _metadata_get(index_metadata, "Owner surface"),
        _metadata_get(index_metadata, "Owner surfaces"),
    )
    for candidate in candidates:
        owner_surfaces = _split_inline_code_or_value(candidate)
        if owner_surfaces:
            return owner_surfaces
    return ("docs/decisions/",)


def discover_decision_repos(
    *,
    workspace_root: Path = DEFAULT_WORKSPACE_ROOT,
    extra_repo_roots: Sequence[Path] = (),
) -> list[Path]:
    candidates: list[Path] = []
    if workspace_root.is_dir():
        candidates.extend(sorted(path for path in workspace_root.iterdir() if path.is_dir()))
    candidates.extend(extra_repo_roots)

    repos: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        root = candidate.resolve()
        if root in seen:
            continue
        seen.add(root)
        if not (root / ".git").exists():
            continue
        if not (root / "docs" / "decisions").is_dir():
            continue
        repos.append(root)
    return sorted(repos, key=lambda path: path.name.lower())


def load_repo_decisions(repo_root: Path) -> tuple[list[WorkspaceDecisionRecord], list[dict[str, str]]]:
    records: list[WorkspaceDecisionRecord] = []
    issues: list[dict[str, str]] = []
    repo = repo_root.name
    decisions_root = repo_root / "docs" / "decisions"
    for path in sorted(decisions_root.glob("*.md")):
        if path.name in EXEMPT_DECISION_FILES:
            continue
        relative_path = path.relative_to(repo_root)
        try:
            text = path.read_text(encoding="utf-8")
            top_metadata = _parse_top_metadata(text)
            index_metadata = _parse_index_metadata(text)
            decision_id = _derive_decision_id(relative_path, top_metadata, index_metadata)
            if not decision_id:
                raise ValueError(f"{relative_path.as_posix()} is missing a parseable decision id")
            records.append(
                WorkspaceDecisionRecord(
                    repo=repo,
                    repo_root=repo_root,
                    decision_id=decision_id,
                    title=_parse_title(text, path=relative_path),
                    status=_derive_status(text, top_metadata, index_metadata),
                    date=_derive_date(top_metadata, index_metadata),
                    path=relative_path,
                    owner_surfaces=_derive_owner_surfaces(top_metadata, index_metadata),
                    metadata_facets=_facet_pairs(index_metadata),
                    source_surfaces=_parse_bullet_section(text, "Source surfaces"),
                    superseded_by=_parse_superseded_by(text),
                    source_sha256=_sha256(path),
                )
            )
        except ValueError as exc:
            issues.append({"repo": repo, "path": relative_path.as_posix(), "error": str(exc)})
    return records, issues


def collect_repo_decision_surfaces(
    repo_root: Path,
    records: Sequence[WorkspaceDecisionRecord],
    parse_issues: Sequence[dict[str, str]] = (),
) -> tuple[list[WorkspaceDecisionSurface], list[dict[str, str]]]:
    surfaces: list[WorkspaceDecisionSurface] = []
    issues: list[dict[str, str]] = []
    repo = repo_root.name
    decisions_root = repo_root / "docs" / "decisions"
    record_paths = {record.repo_path for record in records}
    issue_paths = {
        str(issue.get("path", ""))
        for issue in parse_issues
        if issue.get("repo") == repo and issue.get("path")
    }

    for path in _fingerprint_files(repo_root):
        relative_path = path.relative_to(repo_root)
        repo_path = relative_path.as_posix()
        if repo_path in record_paths or repo_path in issue_paths:
            continue

        decision_relative = path.relative_to(decisions_root)
        if len(decision_relative.parts) == 1 and decision_relative.name in LANE_DOCUMENT_SURFACE_KINDS:
            surfaces.append(
                WorkspaceDecisionSurface(
                    repo=repo,
                    repo_root=repo_root,
                    path=relative_path,
                    surface_kind=LANE_DOCUMENT_SURFACE_KINDS[decision_relative.name],
                    node_type="decision_lane_doc",
                    edge_type="HAS_DECISION_LANE_DOC",
                    source_sha256=_sha256(path),
                )
            )
            continue

        if decision_relative.parts and decision_relative.parts[0] == "indexes":
            surfaces.append(
                WorkspaceDecisionSurface(
                    repo=repo,
                    repo_root=repo_root,
                    path=relative_path,
                    surface_kind="decision_index",
                    node_type="decision_index",
                    edge_type="HAS_DECISION_INDEX",
                    source_sha256=_sha256(path),
                )
            )
            continue

        if len(decision_relative.parts) == 1 and path.suffix.lower() == ".md":
            issues.append(
                {
                    "repo": repo,
                    "path": repo_path,
                    "error": "top-level markdown decision surface was not parsed as a decision record",
                }
            )
            continue

        issues.append(
            {
                "repo": repo,
                "path": repo_path,
                "error": (
                    "unmodeled decision surface: add a registry entry in "
                    "scripts/build_workspace_decision_graph.py or move the file outside docs/decisions/"
                ),
            }
        )

    return surfaces, issues


def collect_workspace_decision_inputs(
    repo_roots: Sequence[Path],
) -> tuple[list[WorkspaceDecisionRecord], list[WorkspaceDecisionSurface], list[dict[str, str]]]:
    records: list[WorkspaceDecisionRecord] = []
    surfaces: list[WorkspaceDecisionSurface] = []
    issues: list[dict[str, str]] = []
    for repo_root in repo_roots:
        repo_records, repo_issues = load_repo_decisions(repo_root)
        repo_surfaces, repo_surface_issues = collect_repo_decision_surfaces(
            repo_root,
            repo_records,
            repo_issues,
        )
        records.extend(repo_records)
        surfaces.extend(repo_surfaces)
        issues.extend(repo_issues)
        issues.extend(repo_surface_issues)
    return records, surfaces, issues


def collect_workspace_decisions(repo_roots: Sequence[Path]) -> tuple[list[WorkspaceDecisionRecord], list[dict[str, str]]]:
    records, _, issues = collect_workspace_decision_inputs(repo_roots)
    return records, issues


def build_workspace_graph(
    records: Sequence[WorkspaceDecisionRecord],
    *,
    surfaces: Sequence[WorkspaceDecisionSurface] = (),
    input_fingerprint: str | None = None,
) -> dict[str, object]:
    nodes: dict[str, dict[str, object]] = {}
    edges: dict[tuple[str, str, str], dict[str, str]] = {}
    by_repo: dict[str, list[WorkspaceDecisionRecord]] = {}
    surfaces_by_repo: dict[str, list[WorkspaceDecisionSurface]] = {}

    def add_node(kind: str, label: str, node_id: str, **properties: object) -> str:
        node = nodes.setdefault(node_id, {"id": node_id, "type": kind, "label": label})
        node.update(properties)
        return node_id

    def add_edge(source: str, target: str, edge_type: str) -> None:
        edges.setdefault((source, target, edge_type), {"source": source, "target": target, "type": edge_type})

    for record in records:
        by_repo.setdefault(record.repo, []).append(record)
    for surface in surfaces:
        surfaces_by_repo.setdefault(surface.repo, []).append(surface)

    repo_names = sorted(set(by_repo) | set(surfaces_by_repo))
    for repo in repo_names:
        repo_records = by_repo.get(repo, [])
        repo_surfaces = surfaces_by_repo.get(repo, [])
        repo_root = repo_records[0].repo_root if repo_records else repo_surfaces[0].repo_root
        repo_id = add_node("repo", repo, _node_id("repo", repo), source_root=repo_root.as_posix())
        lane_id = add_node(
            "decision_lane",
            f"{repo}/docs/decisions",
            _node_id("decision_lane", repo),
            path="docs/decisions",
        )
        add_edge(repo_id, lane_id, "HAS_DECISION_LANE")

        for surface in sorted(repo_surfaces, key=lambda item: (item.node_type, item.repo_path)):
            surface_id = add_node(
                surface.node_type,
                surface.repo_path,
                _node_id(surface.node_type, repo, surface.repo_path),
                repo=repo,
                path=surface.repo_path,
                surface_kind=surface.surface_kind,
                source_sha256=surface.source_sha256,
            )
            add_edge(lane_id, surface_id, surface.edge_type)

        previous_decision_node: str | None = None
        for record in sorted(repo_records, key=lambda item: (item.date, item.decision_id, item.repo_path)):
            decision_id = _node_id("decision", record.repo, record.decision_id)
            add_node(
                "decision",
                record.decision_id,
                decision_id,
                repo=record.repo,
                title=record.title,
                status=record.status,
                date=record.date,
                path=record.repo_path,
                source_sha256=record.source_sha256,
            )
            add_edge(lane_id, decision_id, "CONTAINS_DECISION")
            if previous_decision_node is not None:
                add_edge(previous_decision_node, decision_id, "NEXT_DECISION_IN_REPO")
            previous_decision_node = decision_id

            status_id = add_node("status", record.status, _node_id("status", record.status))
            date_id = add_node("date", record.date, _node_id("date", record.date))
            add_edge(decision_id, status_id, "HAS_STATUS")
            add_edge(decision_id, date_id, "DATED")

            for owner_surface in record.owner_surfaces:
                surface_id = add_node(
                    "owner_surface",
                    owner_surface,
                    _node_id("owner_surface", record.repo, owner_surface),
                    repo=record.repo,
                )
                add_edge(decision_id, surface_id, "OWNED_BY_SURFACE")
            for facet_key, facet_values in record.metadata_facets:
                for facet_value in facet_values:
                    facet_id = add_node(
                        "decision_facet",
                        facet_value,
                        _node_id("decision_facet", facet_key, facet_value),
                        facet_key=facet_key,
                    )
                    add_edge(decision_id, facet_id, "HAS_DECISION_FACET")
            for source_surface in record.source_surfaces:
                source_id = add_node(
                    "source_surface",
                    source_surface,
                    _node_id("source_surface", record.repo, source_surface),
                    repo=record.repo,
                )
                add_edge(decision_id, source_id, "CITES_SOURCE_SURFACE")
            for superseded_by in record.superseded_by:
                add_edge(decision_id, _node_id("decision", record.repo, superseded_by), "SUPERSEDED_BY")

        indexes_root = repo_root / "docs" / "decisions" / "indexes"
        if not repo_surfaces and indexes_root.is_dir():
            for index_path in sorted(indexes_root.glob("*")):
                if not index_path.is_file():
                    continue
                rel_path = index_path.relative_to(repo_root).as_posix()
                index_id = add_node(
                    "decision_index",
                    rel_path,
                    _node_id("decision_index", repo, rel_path),
                    repo=repo,
                    path=rel_path,
                    source_sha256=_sha256(index_path),
                )
                add_edge(lane_id, index_id, "HAS_DECISION_INDEX")

    node_values = sorted(nodes.values(), key=lambda item: str(item["id"]))
    edge_values = sorted(edges.values(), key=lambda item: (item["source"], item["type"], item["target"]))
    repo_counts = {repo: len(by_repo.get(repo, [])) for repo in repo_names}
    node_type_counts: dict[str, int] = {}
    edge_type_counts: dict[str, int] = {}
    for node in node_values:
        node_type = str(node["type"])
        node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1
    for edge in edge_values:
        edge_type = edge["type"]
        edge_type_counts[edge_type] = edge_type_counts.get(edge_type, 0) + 1
    surface_kind_counts: dict[str, int] = {"decision_record": len(records)}
    for surface in surfaces:
        surface_kind_counts[surface.surface_kind] = surface_kind_counts.get(surface.surface_kind, 0) + 1

    return {
        "schema": GRAPH_SCHEMA,
        "authority_note": "Repo-local decision records own rationale; this workspace graph is a generated navigation read model.",
        "input_fingerprint": input_fingerprint,
        "repo_count": len(repo_names),
        "decision_count": len(records),
        "decision_surface_count": len(records) + len(surfaces),
        "node_count": len(node_values),
        "edge_count": len(edge_values),
        "repo_decision_counts": repo_counts,
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "surface_kind_counts": dict(sorted(surface_kind_counts.items())),
        "nodes": node_values,
        "edges": edge_values,
    }


def graph_summary(graph: dict[str, object], issues: Sequence[dict[str, str]]) -> dict[str, object]:
    return {
        "schema": GRAPH_SUMMARY_SCHEMA,
        "input_fingerprint": graph["input_fingerprint"],
        "repo_count": graph["repo_count"],
        "decision_count": graph["decision_count"],
        "decision_surface_count": graph["decision_surface_count"],
        "node_count": graph["node_count"],
        "edge_count": graph["edge_count"],
        "repo_decision_counts": graph["repo_decision_counts"],
        "node_type_counts": graph["node_type_counts"],
        "edge_type_counts": graph["edge_type_counts"],
        "surface_kind_counts": graph["surface_kind_counts"],
        "issue_count": len(issues),
        "issues": list(issues),
    }


def write_graph_outputs(graph: dict[str, object], issues: Sequence[dict[str, str]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "workspace_decision_graph.json").write_text(
        json.dumps(graph, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(graph_summary(graph, issues), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "nodes.jsonl").open("w", encoding="utf-8") as handle:
        for node in graph["nodes"]:
            handle.write(json.dumps(node, ensure_ascii=True, sort_keys=True) + "\n")
    with (output_dir / "edges.jsonl").open("w", encoding="utf-8") as handle:
        for edge in graph["edges"]:
            handle.write(json.dumps(edge, ensure_ascii=True, sort_keys=True) + "\n")


def output_matches(graph: dict[str, object], issues: Sequence[dict[str, str]], output_dir: Path) -> bool:
    expected = {
        "workspace_decision_graph.json": json.dumps(graph, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        "summary.json": json.dumps(graph_summary(graph, issues), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
    }
    for name, text in expected.items():
        path = output_dir / name
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            return False
    nodes_path = output_dir / "nodes.jsonl"
    edges_path = output_dir / "edges.jsonl"
    if not nodes_path.is_file() or not edges_path.is_file():
        return False
    expected_nodes = "".join(json.dumps(node, ensure_ascii=True, sort_keys=True) + "\n" for node in graph["nodes"])
    expected_edges = "".join(json.dumps(edge, ensure_ascii=True, sort_keys=True) + "\n" for edge in graph["edges"])
    return nodes_path.read_text(encoding="utf-8") == expected_nodes and edges_path.read_text(encoding="utf-8") == expected_edges


def _default_extra_repos() -> list[Path]:
    if DEFAULT_LOCAL_STACK_ROOT.is_dir():
        return [DEFAULT_LOCAL_STACK_ROOT]
    return []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--repo-root", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write", action="store_true", help="write graph JSON and JSONL outputs")
    parser.add_argument("--check", action="store_true", help="fail if output-dir is missing or stale")
    parser.add_argument("--json", action="store_true", help="print summary JSON")
    args = parser.parse_args(argv)

    extra_roots = list(args.repo_root) or _default_extra_repos()
    repo_roots = discover_decision_repos(
        workspace_root=args.workspace_root,
        extra_repo_roots=extra_roots,
    )
    records, surfaces, issues = collect_workspace_decision_inputs(repo_roots)
    graph = build_workspace_graph(records, surfaces=surfaces, input_fingerprint=workspace_input_fingerprint(repo_roots))
    summary = graph_summary(graph, issues)

    if args.write:
        write_graph_outputs(graph, issues, args.output_dir)
    if args.check and not output_matches(graph, issues, args.output_dir):
        print(f"workspace decision graph is stale; run {Path(__file__).as_posix()} --write", flush=True)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    else:
        print(
            "workspace decision graph: "
            f"{summary['repo_count']} repos, {summary['decision_count']} decisions, "
            f"{summary['node_count']} nodes, {summary['edge_count']} edges, "
            f"{summary['issue_count']} issues"
        )
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
