from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")
DEFAULT_STACK_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_OUTPUT_DIR = Path("Logs/decision-graph/latest")
GRAPH_FILE = "workspace_decision_graph.json"
SUMMARY_FILE = "summary.json"
LOCK_NAME = ".refresh.lock"


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _contains(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return needle in value.lower()
    if isinstance(value, dict):
        return any(_contains(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return False


def _path_matches(surface: str, path: str) -> bool:
    surface_value = surface.strip().strip("`").lstrip("./").lower()
    path_value = path.strip().strip("`").lstrip("./").lower()
    if not surface_value or not path_value:
        return False
    surface_prefix = surface_value.rstrip("/") + "/"
    path_prefix = path_value.rstrip("/") + "/"
    return (
        surface_value == path_value
        or surface_value in path_value
        or path_value in surface_value
        or path_value.startswith(surface_prefix)
        or surface_value.startswith(path_prefix)
    )


def _is_route_anchor_node(node: dict[str, Any]) -> bool:
    return node.get("type") == "decision_facet" and node.get("facet_key") == "Route anchors"


@dataclass(slots=True)
class AoADecisionsMCPState:
    workspace_root: Path
    stack_root: Path
    output_dir: Path
    include_stack_repo: bool = True

    @classmethod
    def discover(
        cls,
        workspace_root: str | Path | None = None,
        stack_root: str | Path | None = None,
        output_dir: str | Path | None = None,
        include_stack_repo: bool = True,
    ) -> "AoADecisionsMCPState":
        stack = Path(
            stack_root
            or os.environ.get("AOA_ABYSS_STACK_ROOT")
            or DEFAULT_STACK_ROOT
        ).expanduser().resolve()
        output = Path(
            output_dir
            or os.environ.get("AOA_DECISIONS_GRAPH_DIR")
            or DEFAULT_OUTPUT_DIR
        ).expanduser()
        if not output.is_absolute():
            output = stack / output
        return cls(
            workspace_root=Path(
                workspace_root
                or os.environ.get("AOA_WORKSPACE_ROOT")
                or DEFAULT_WORKSPACE_ROOT
            ).expanduser().resolve(),
            stack_root=stack,
            output_dir=output.resolve(),
            include_stack_repo=include_stack_repo,
        )

    @property
    def graph_path(self) -> Path:
        return self.output_dir / GRAPH_FILE

    @property
    def summary_path(self) -> Path:
        return self.output_dir / SUMMARY_FILE

    def _builder(self) -> ModuleType:
        path = self.stack_root / "scripts" / "build_workspace_decision_graph.py"
        if not path.is_file():
            raise FileNotFoundError(f"missing decision graph builder: {path}")
        spec = importlib.util.spec_from_file_location("aoa_workspace_decision_graph_builder", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load decision graph builder: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def repo_roots(self) -> list[Path]:
        builder = self._builder()
        extras = [self.stack_root] if self.include_stack_repo else []
        return builder.discover_decision_repos(
            workspace_root=self.workspace_root,
            extra_repo_roots=extras,
        )

    def current_input_fingerprint(self) -> str:
        builder = self._builder()
        return builder.workspace_input_fingerprint(self.repo_roots())

    def cached_summary(self) -> dict[str, Any] | None:
        summary = _read_json(self.summary_path)
        return summary if isinstance(summary, dict) else None

    def cache_is_fresh(self) -> bool:
        summary = self.cached_summary()
        if not summary or not self.graph_path.is_file():
            return False
        return summary.get("input_fingerprint") == self.current_input_fingerprint()

    @contextmanager
    def _refresh_lock(self) -> Iterator[None]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = self.output_dir / LOCK_NAME
        acquired = False
        for _ in range(200):
            try:
                lock_dir.mkdir()
                acquired = True
                break
            except FileExistsError:
                try:
                    if time.time() - lock_dir.stat().st_mtime > 600:
                        lock_dir.rmdir()
                        continue
                except OSError:
                    pass
                time.sleep(0.05)
        if not acquired:
            raise TimeoutError(f"timed out waiting for decision graph refresh lock: {lock_dir}")
        try:
            yield
        finally:
            try:
                lock_dir.rmdir()
            except OSError:
                pass

    def ensure_fresh(self, force: bool = False) -> dict[str, Any]:
        before = self.cached_summary()
        before_fingerprint = before.get("input_fingerprint") if before else None
        current_fingerprint = self.current_input_fingerprint()
        if not force and before_fingerprint == current_fingerprint and self.graph_path.is_file():
            return self._freshness_payload(refreshed=False, status="fresh", summary=before)

        with self._refresh_lock():
            if not force and self.cache_is_fresh():
                return self._freshness_payload(refreshed=False, status="fresh", summary=self.cached_summary())

            builder = self._builder()
            repo_roots = self.repo_roots()
            records, surfaces, issues = builder.collect_workspace_decision_inputs(repo_roots)
            fingerprint = builder.workspace_input_fingerprint(repo_roots)
            graph = builder.build_workspace_graph(records, surfaces=surfaces, input_fingerprint=fingerprint)
            builder.write_graph_outputs(graph, issues, self.output_dir)
            summary = builder.graph_summary(graph, issues)
            status = "refreshed" if not issues else "refreshed-with-issues"
            return self._freshness_payload(refreshed=True, status=status, summary=summary)

    def _freshness_payload(
        self,
        *,
        refreshed: bool,
        status: str,
        summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        summary = summary or {}
        return {
            "schema": "aoa_decisions_graph_freshness_v1",
            "status": status,
            "refreshed": refreshed,
            "output_dir": self.output_dir.as_posix(),
            "graph_path": self.graph_path.as_posix(),
            "summary_path": self.summary_path.as_posix(),
            "input_fingerprint": summary.get("input_fingerprint"),
            "repo_count": summary.get("repo_count", 0),
            "decision_count": summary.get("decision_count", 0),
            "decision_surface_count": summary.get("decision_surface_count", 0),
            "node_count": summary.get("node_count", 0),
            "edge_count": summary.get("edge_count", 0),
            "issue_count": summary.get("issue_count", 0),
        }

    def graph(self) -> dict[str, Any]:
        freshness = self.ensure_fresh()
        payload = _read_json(self.graph_path)
        if not isinstance(payload, dict):
            raise RuntimeError(f"decision graph is not readable after refresh: {self.graph_path}")
        payload.setdefault("freshness", freshness)
        return payload

    def summary(self) -> dict[str, Any]:
        freshness = self.ensure_fresh()
        summary = self.cached_summary()
        if not isinstance(summary, dict):
            raise RuntimeError(f"decision graph summary is not readable after refresh: {self.summary_path}")
        return {**summary, "freshness": freshness}

    def repo(self, repo: str) -> dict[str, Any]:
        graph = self.graph()
        decision_nodes = [
            node
            for node in graph.get("nodes", [])
            if node.get("type") == "decision" and node.get("repo") == repo
        ]
        decision_ids = {node["id"] for node in decision_nodes}
        related_edges = [
            edge
            for edge in graph.get("edges", [])
            if edge.get("source") in decision_ids or edge.get("target") in decision_ids
        ]
        return {
            "schema": "aoa_decisions_repo_packet_v1",
            "repo": repo,
            "freshness": graph["freshness"],
            "decision_count": len(decision_nodes),
            "decisions": decision_nodes,
            "edges": related_edges,
            "authority_note": graph.get("authority_note"),
        }

    def decision(self, decision_id: str, repo: str | None = None) -> dict[str, Any]:
        graph = self.graph()
        needle = decision_id.upper()
        matches = []
        for node in graph.get("nodes", []):
            if node.get("type") != "decision":
                continue
            if repo and node.get("repo") != repo:
                continue
            if str(node.get("label", "")).upper() == needle or str(node.get("id", "")).upper().endswith(":" + needle):
                matches.append(node)
        related_ids = {node["id"] for node in matches}
        related_edges = [
            edge
            for edge in graph.get("edges", [])
            if edge.get("source") in related_ids or edge.get("target") in related_ids
        ]
        neighbor_ids = {
            endpoint
            for edge in related_edges
            for endpoint in (edge.get("source"), edge.get("target"))
            if isinstance(endpoint, str)
        }
        related_nodes = [node for node in graph.get("nodes", []) if node.get("id") in neighbor_ids]
        return {
            "schema": "aoa_decisions_decision_packet_v1",
            "decision_id": decision_id,
            "repo": repo,
            "freshness": graph["freshness"],
            "matches": matches,
            "nodes": related_nodes,
            "edges": related_edges,
            "authority_note": graph.get("authority_note"),
        }

    def search(self, query: str, repo: str | None = None, limit: int = 20) -> dict[str, Any]:
        graph = self.graph()
        needle = query.lower().strip()
        results: list[dict[str, Any]] = []
        for node in graph.get("nodes", []):
            if node.get("type") != "decision":
                continue
            if repo and node.get("repo") != repo:
                continue
            if needle and not _contains(node, needle):
                continue
            results.append(node)
            if len(results) >= limit:
                break
        return {
            "schema": "aoa_decisions_search_v1",
            "query": query,
            "repo": repo,
            "freshness": graph["freshness"],
            "count": len(results),
            "results": results,
        }

    def packet(
        self,
        *,
        query: str = "",
        repo: str | None = None,
        decision_id: str | None = None,
        path: str | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        graph = self.graph()
        candidates: list[dict[str, Any]] = []
        query_text = query.lower().strip()
        path_decision_ids, path_edges, _path_surfaces = self._path_impact(graph, path or "", repo=repo)
        for node in graph.get("nodes", []):
            if node.get("type") != "decision":
                continue
            if repo and node.get("repo") != repo:
                continue
            if decision_id and str(node.get("label", "")).upper() != decision_id.upper():
                continue
            if path and node.get("id") not in path_decision_ids and not _path_matches(str(node.get("path", "")), path):
                continue
            if query_text and not _contains(node, query_text):
                continue
            candidates.append(node)
            if len(candidates) >= limit:
                break
        decision_ids = {node["id"] for node in candidates}
        related_edges = [
            edge
            for edge in graph.get("edges", [])
            if edge.get("source") in decision_ids or edge.get("target") in decision_ids
        ]
        if path:
            related_edges.extend(
                edge
                for edge in path_edges
                if edge.get("source") in decision_ids and edge not in related_edges
            )
        related_node_ids = {
            endpoint
            for edge in related_edges
            for endpoint in (edge.get("source"), edge.get("target"))
            if isinstance(endpoint, str)
        } | decision_ids
        related_nodes = [node for node in graph.get("nodes", []) if node.get("id") in related_node_ids]
        return {
            "schema": "aoa_decisions_packet_v1",
            "query": query,
            "repo": repo,
            "decision_id": decision_id,
            "path": path,
            "freshness": graph["freshness"],
            "decision_count": len(candidates),
            "decisions": candidates,
            "nodes": related_nodes,
            "edges": related_edges,
            "authority_order": [
                "repo-local docs/decisions/*.md",
                "repo-local generated decision indexes",
                "workspace decision graph",
                "MCP packet",
            ],
        }

    def source_surface(self, source_surface: str, repo: str | None = None, limit: int = 50) -> dict[str, Any]:
        return self._surface_packet(
            schema="aoa_decisions_source_surface_packet_v1",
            query=source_surface,
            repo=repo,
            surface_node_type="source_surface",
            edge_type="CITES_SOURCE_SURFACE",
            limit=limit,
        )

    def owner_surface(self, owner_surface: str, repo: str | None = None, limit: int = 50) -> dict[str, Any]:
        return self._surface_packet(
            schema="aoa_decisions_owner_surface_packet_v1",
            query=owner_surface,
            repo=repo,
            surface_node_type="owner_surface",
            edge_type="OWNED_BY_SURFACE",
            limit=limit,
        )

    def _surface_packet(
        self,
        *,
        schema: str,
        query: str,
        repo: str | None,
        surface_node_type: str,
        edge_type: str,
        limit: int,
    ) -> dict[str, Any]:
        graph = self.graph()
        query_text = query.lower().strip()
        matched_surface_nodes = [
            node
            for node in graph.get("nodes", [])
            if node.get("type") == surface_node_type
            and (not repo or node.get("repo") == repo)
            and (not query_text or query_text in str(node.get("label", "")).lower())
        ]
        surface_ids = {node["id"] for node in matched_surface_nodes}
        matched_edges = [
            edge
            for edge in graph.get("edges", [])
            if edge.get("type") == edge_type and edge.get("target") in surface_ids
        ]
        decision_ids = {edge["source"] for edge in matched_edges if isinstance(edge.get("source"), str)}
        decisions = [
            node
            for node in graph.get("nodes", [])
            if node.get("type") == "decision" and node.get("id") in decision_ids
        ][:limit]
        limited_decision_ids = {node["id"] for node in decisions}
        related_edges = [
            edge
            for edge in matched_edges
            if edge.get("source") in limited_decision_ids
        ]
        return {
            "schema": schema,
            "query": query,
            "repo": repo,
            "freshness": graph["freshness"],
            "decision_count": len(decisions),
            "decisions": decisions,
            "surfaces": matched_surface_nodes,
            "edges": related_edges,
            "authority_order": [
                "repo-local docs/decisions/*.md",
                "workspace decision graph",
                "MCP packet",
            ],
        }

    def changed_path(self, path: str, repo: str | None = None, limit: int = 50) -> dict[str, Any]:
        graph = self.graph()
        decision_ids, matched_edges, surface_nodes = self._path_impact(graph, path, repo=repo)
        decisions = [
            node
            for node in graph.get("nodes", [])
            if node.get("type") == "decision" and node.get("id") in decision_ids
        ][:limit]
        limited_decision_ids = {node["id"] for node in decisions}
        related_edges = [edge for edge in matched_edges if edge.get("source") in limited_decision_ids]
        return {
            "schema": "aoa_decisions_changed_path_packet_v1",
            "path": path,
            "repo": repo,
            "freshness": graph["freshness"],
            "decision_count": len(decisions),
            "decisions": decisions,
            "surfaces": surface_nodes,
            "edges": related_edges,
            "authority_order": [
                "repo-local docs/decisions/*.md",
                "workspace decision graph",
                "MCP packet",
            ],
        }

    def _path_impact(
        self,
        graph: dict[str, Any],
        path: str,
        *,
        repo: str | None,
    ) -> tuple[set[str], list[dict[str, Any]], list[dict[str, Any]]]:
        surface_nodes = [
            node
            for node in graph.get("nodes", [])
            if node.get("type") in {"source_surface", "owner_surface"}
            and (not repo or node.get("repo") == repo)
            and _path_matches(str(node.get("label", "")), path)
        ]
        route_anchor_nodes = [
            node
            for node in graph.get("nodes", [])
            if _is_route_anchor_node(node)
            and _path_matches(str(node.get("label", "")), path)
        ]
        surface_ids = {node["id"] for node in [*surface_nodes, *route_anchor_nodes]}
        matched_edges = [
            edge
            for edge in graph.get("edges", [])
            if edge.get("target") in surface_ids
            and edge.get("type") in {"CITES_SOURCE_SURFACE", "OWNED_BY_SURFACE", "HAS_DECISION_FACET"}
        ]
        if repo:
            repo_decision_ids = {
                node["id"]
                for node in graph.get("nodes", [])
                if node.get("type") == "decision" and node.get("repo") == repo
            }
            matched_edges = [
                edge
                for edge in matched_edges
                if edge.get("source") in repo_decision_ids
            ]
        decision_ids = {edge["source"] for edge in matched_edges if isinstance(edge.get("source"), str)}
        matched_surface_ids = {edge["target"] for edge in matched_edges if isinstance(edge.get("target"), str)}
        matched_surface_nodes = [
            node
            for node in [*surface_nodes, *route_anchor_nodes]
            if node.get("id") in matched_surface_ids
        ]
        return decision_ids, matched_edges, matched_surface_nodes

    def repo_symmetry(self, repo: str | None = None) -> dict[str, Any]:
        graph = self.graph()
        summary = self.summary()
        repo_names = sorted(summary.get("repo_decision_counts", {}).keys())
        if repo:
            repo_names = [name for name in repo_names if name == repo]
        issue_counts: dict[str, int] = {}
        for issue in summary.get("issues", []):
            if isinstance(issue, dict):
                issue_repo = str(issue.get("repo", ""))
                issue_counts[issue_repo] = issue_counts.get(issue_repo, 0) + 1

        repo_packets: list[dict[str, Any]] = []
        for repo_name in repo_names:
            lane_docs = [
                node
                for node in graph.get("nodes", [])
                if node.get("type") == "decision_lane_doc" and node.get("repo") == repo_name
            ]
            indexes = [
                node
                for node in graph.get("nodes", [])
                if node.get("type") == "decision_index" and node.get("repo") == repo_name
            ]
            surface_kinds = sorted({str(node.get("surface_kind")) for node in lane_docs if node.get("surface_kind")})
            repo_packets.append(
                {
                    "repo": repo_name,
                    "decision_count": summary.get("repo_decision_counts", {}).get(repo_name, 0),
                    "lane_doc_count": len(lane_docs),
                    "decision_index_count": len(indexes),
                    "lane_doc_surface_kinds": surface_kinds,
                    "issue_count": issue_counts.get(repo_name, 0),
                    "symmetry_note": "compare coverage posture; do not force identical repo structure",
                }
            )
        return {
            "schema": "aoa_decisions_repo_symmetry_packet_v1",
            "repo": repo,
            "freshness": graph["freshness"],
            "repo_count": len(repo_packets),
            "repos": repo_packets,
            "authority_note": graph.get("authority_note"),
        }

    def issues(self, repo: str | None = None, limit: int = 100) -> dict[str, Any]:
        summary = self.summary()
        issues = [
            issue
            for issue in summary.get("issues", [])
            if isinstance(issue, dict) and (not repo or issue.get("repo") == repo)
        ][:limit]
        return {
            "schema": "aoa_decisions_issues_packet_v1",
            "repo": repo,
            "freshness": summary["freshness"],
            "issue_count": len(issues),
            "issues": issues,
            "summary_issue_count": summary.get("issue_count", 0),
        }

    def read_resource(self, uri: str) -> dict[str, Any]:
        prefix = "aoa-decisions://"
        if not uri.startswith(prefix):
            return {"schema": "aoa_decisions_resource_error_v1", "error": f"unsupported uri: {uri}"}
        route = uri[len(prefix) :]
        if route == "status":
            return self.ensure_fresh()
        if route == "summary":
            return self.summary()
        if route.startswith("repo/"):
            return self.repo(route.split("/", 1)[1])
        if route.startswith("decision/"):
            return self.decision(route.split("/", 1)[1])
        if route.startswith("issues"):
            _, _, repo = route.partition("/")
            return self.issues(repo=repo or None)
        return {"schema": "aoa_decisions_resource_error_v1", "error": f"unknown resource route: {uri}"}

    def render_resource(self, uri: str) -> str:
        return _json(self.read_resource(uri))
