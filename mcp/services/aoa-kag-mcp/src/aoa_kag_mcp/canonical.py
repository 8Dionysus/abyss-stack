from __future__ import annotations

import importlib.util
import json
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .core import AoAKagMCPState


def _is_retrieval_fixture(path: str) -> bool:
    folded = f"/{path.casefold()}/"
    name = Path(path).name.casefold()
    return (
        any(
            part in folded
            for part in ("/fixtures/", "/fixture/", "/testdata/", "/golden/")
        )
        or "retrieval-eval." in name
        or "retrieval_eval." in name
        or ".fixture." in name
        or "_fixture." in name
    )


class CanonicalRepoKag:
    """Bounded adapter over the canonical repo-local query implementation."""

    def __init__(self, state: AoAKagMCPState, *, cache_size: int = 2) -> None:
        self.state = state
        self.cache_size = max(cache_size, 1)
        self._cache: OrderedDict[str, tuple[tuple[int, int], Any]] = OrderedDict()
        self._lock = threading.RLock()
        self._loader: Any | None = None

    def _query_module(self) -> Any:
        with self._lock:
            if self._loader is not None:
                return self._loader
            script_root = self.state.aoa_kag_root / "scripts"
            query_path = script_root / "query_repo_local_kag.py"
            if not query_path.is_file():
                raise RuntimeError(
                    f"canonical KAG query module is unavailable: {query_path}"
                )
            spec = importlib.util.spec_from_file_location(
                "_aoa_kag_owner_query_repo_local_kag",
                query_path,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError(
                    f"cannot load canonical KAG query module: {query_path}"
                )
            module = importlib.util.module_from_spec(spec)
            script_path = script_root.as_posix()
            sys.path.insert(0, script_path)
            try:
                spec.loader.exec_module(module)
            finally:
                sys.path.remove(script_path)
            if not callable(getattr(module, "load_family", None)) or not callable(
                getattr(module, "RepoKagQuery", None)
            ):
                raise RuntimeError(
                    f"canonical KAG query module has an invalid interface: {query_path}"
                )
            self._loader = module
            return self._loader

    def _family_path(self, repo: str) -> Path | None:
        path = self.state.canonical_family_path(repo)
        return path if path and path.is_file() else None

    def _query(self, repo: str) -> Any:
        family_path = self._family_path(repo)
        if family_path is None:
            raise RuntimeError(f"canonical KAG family is unavailable for {repo}")
        stat = family_path.stat()
        identity = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._cache.get(repo)
            if cached and cached[0] == identity:
                self._cache.move_to_end(repo)
                return cached[1]
        module = self._query_module()
        provider_root = self.state.provider_root(repo)
        if self.state.artifact_root is None:
            # Keep the pre-v4 portable loader ABI available for owners whose
            # query module has not adopted the optional delivery arguments.
            loaded = module.load_family(provider_root)
        else:
            loaded = module.load_family(
                provider_root,
                artifact_root=self.state.artifact_root,
                allow_shadow_git=False,
            )
        if not isinstance(loaded, (tuple, list)) or len(loaded) < 2:
            raise RuntimeError("canonical KAG load_family returned an invalid family")
        source_index, family = loaded[0], loaded[1]
        if self.state.artifact_root is None:
            query = module.RepoKagQuery(source_index, family)
        else:
            query = module.RepoKagQuery(source_index, family, repo_root=provider_root)
        with self._lock:
            self._cache[repo] = (identity, query)
            self._cache.move_to_end(repo)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return query

    def owner_names(self) -> list[str]:
        return sorted(
            str(provider.get("repo"))
            for provider in self.state.providers()
            if provider.get("repo")
        )

    def owner_digest(self, repo: str) -> str | None:
        path = self.state.canonical_family_path(repo)
        if path is None or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        index_identity = payload.get("index_identity")
        if isinstance(index_identity, dict):
            value = index_identity.get("content_digest")
            return str(value) if value else None

        family_identity = payload.get("family_identity")
        source_snapshot = (
            family_identity.get("source_snapshot")
            if isinstance(family_identity, dict)
            else None
        )
        source_header = payload.get("source_index_header")
        header_identity = (
            source_header.get("index_identity")
            if isinstance(source_header, dict)
            else None
        )
        header_digest = (
            header_identity.get("content_digest")
            if isinstance(header_identity, dict)
            else None
        )
        compatibility = payload.get("compatibility")
        files = compatibility.get("files") if isinstance(compatibility, dict) else None
        source_file_digests = (
            {
                str(item.get("content_digest"))
                for item in files
                if isinstance(item, dict)
                and item.get("kind") == "source"
                and item.get("content_digest")
            }
            if isinstance(files, list)
            else set()
        )
        digests = {
            str(source_snapshot).removeprefix("sha256:") if source_snapshot else "",
            str(header_digest or ""),
            *source_file_digests,
        }
        digests.discard("")
        if len(digests) > 1:
            raise RuntimeError(
                f"canonical KAG source-index identities disagree for {repo}"
            )
        return next(iter(digests), None)

    def resolve_owner(self, record_id: str) -> str | None:
        parts = record_id.split(":", 3)
        namespace_owner = parts[1] if len(parts) == 4 and parts[0] == "aoa" else ""
        if not namespace_owner:
            return None
        return next(
            (
                repo
                for repo in self.owner_names()
                if repo.casefold() == namespace_owner.casefold()
            ),
            None,
        )

    def owner_manifest(self, repo: str) -> dict[str, Any] | None:
        try:
            return self.state.provider_manifest(repo)
        except (KeyError, OSError, RuntimeError, ValueError):
            return None

    def schema(self, name: str) -> dict[str, Any] | None:
        filename = name if name.endswith(".schema.json") else f"{name}.schema.json"
        if Path(filename).name != filename:
            raise ValueError("schema name must be a filename")
        path = (self.state.aoa_kag_root / "schemas" / filename).resolve()
        try:
            path.relative_to((self.state.aoa_kag_root / "schemas").resolve())
        except ValueError as exc:
            raise ValueError("schema path escapes aoa-kag schemas") from exc
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None

    def discover_owner(self, repo: str) -> dict[str, Any] | None:
        try:
            return self._query(repo).discover()
        except RuntimeError:
            return None

    def search_owner(
        self,
        repo: str,
        query: str,
        *,
        strategy: str,
        record_class: str | None,
        kind: str | None,
        document_role: str | None,
        surface_state: str | None,
        path_prefix: str,
        access_scopes: set[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        engine = self._query(repo)
        node_classes = {record_class} if record_class else None
        fetch_limit = min(max(limit * 4, limit), 500)
        if strategy == "exact":
            hits = engine.exact(
                query,
                limit=fetch_limit,
                node_classes=node_classes,
                access_scopes=access_scopes,
            )
        elif strategy == "lexical":
            hits = engine.lexical(
                query,
                limit=fetch_limit,
                node_classes=node_classes,
                access_scopes=access_scopes,
            )
        elif strategy == "graph":
            hits = engine.graph(
                query,
                limit=fetch_limit,
                access_scopes=access_scopes,
            )
        else:
            hits = engine.hybrid(
                query,
                limit=fetch_limit,
                access_scopes=access_scopes,
            )
        filtered = [
            hit
            for hit in hits
            if (not record_class or hit.get("node_class") == record_class)
            and (not kind or hit.get("kind") == kind)
            and (
                not document_role
                or (
                    document_role == "evaluation_fixture"
                    and _is_retrieval_fixture(str(hit.get("path") or ""))
                )
                or any(
                    source.get("document_role") == document_role
                    for source in hit.get("sources", [])
                    if isinstance(source, dict)
                )
            )
            and (
                document_role is not None
                or not _is_retrieval_fixture(str(hit.get("path") or ""))
            )
            and (
                not surface_state
                or hit.get("surface_state") == surface_state
                or any(
                    source.get("surface_state") == surface_state
                    for source in hit.get("sources", [])
                    if isinstance(source, dict)
                )
            )
            and (not path_prefix or str(hit.get("path") or "").startswith(path_prefix))
        ]
        if strategy == "exact":
            folded = query.casefold()
            filtered.sort(
                key=lambda hit: (
                    0 if str(hit.get("id") or "").casefold() == folded else 1,
                    0
                    if hit.get("node_class") == "artifact"
                    and str(hit.get("path") or "").casefold() == folded
                    else 1,
                    0 if str(hit.get("path") or "").casefold() == folded else 1,
                    0 if str(hit.get("label") or "").casefold() == folded else 1,
                    str(hit.get("id") or ""),
                )
            )
        return filtered[:limit]

    def read_record(
        self,
        repo: str,
        record_id: str,
        *,
        access_scopes: set[str],
    ) -> dict[str, Any] | None:
        return self._query(repo).read(record_id, access_scopes=access_scopes)

    def traverse_owner(
        self,
        repo: str,
        source_ids: list[str],
        *,
        query: str,
        relation_kinds: set[str] | None,
        max_depth: int,
        access_scopes: set[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        return self._query(repo).traverse(
            source_ids,
            query=query,
            max_hops=max_depth,
            limit=limit,
            relation_kinds=relation_kinds,
            access_scopes=access_scopes,
        )
