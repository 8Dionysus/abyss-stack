from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import threading
import time
import unicodedata
import uuid
from collections import OrderedDict, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol, Sequence
from urllib.parse import quote, unquote, urlparse

from . import exact, graph, vector
from .transport import JsonHttpClient


RESULT_SCHEMA_VERSION = "aoa-kag-mcp-result-v1"
CAPABILITY_SCHEMA_VERSION = "aoa-kag-mcp-capabilities-v1"
SEARCH_STRATEGIES = ("auto", "exact", "lexical", "semantic", "hybrid", "graph")
DETAIL_LEVELS = ("compact", "summary", "full")
MAX_PAGE_SIZE = 10
MAX_TRAVERSAL_DEPTH = 4
MAX_FULL_TEXT_CHARS = 4096
MAX_CONTENT_INSPECTION_FINDINGS = 16


def _content_inspection(fields: dict[str, Any]) -> dict[str, Any] | None:
    findings: list[dict[str, Any]] = []
    finding_count = 0
    for field, value in fields.items():
        if not isinstance(value, str):
            continue
        for offset, character in enumerate(value):
            category = unicodedata.category(character)
            if not category.startswith("C") or character in {"\n", "\r", "\t"}:
                continue
            finding_count += 1
            if len(findings) < MAX_CONTENT_INSPECTION_FINDINGS:
                findings.append(
                    {
                        "field": field,
                        "offset": offset,
                        "code_point": f"U+{ord(character):04X}",
                        "category": category,
                        "name": unicodedata.name(character, "UNNAMED"),
                    }
                )
    if not findings:
        return None
    return {
        "state": "flagged",
        "finding_count": finding_count,
        "findings": findings,
        "truncated": finding_count > len(findings),
    }


class CanonicalKag(Protocol):
    def owner_names(self) -> list[str]: ...

    def owner_digest(self, repo: str) -> str | None: ...

    def resolve_owner(self, record_id: str) -> str | None: ...

    def owner_manifest(self, repo: str) -> dict[str, Any] | None: ...

    def schema(self, name: str) -> dict[str, Any] | None: ...

    def discover_owner(self, repo: str) -> dict[str, Any] | None: ...

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
    ) -> list[dict[str, Any]]: ...

    def read_record(
        self,
        repo: str,
        record_id: str,
        *,
        access_scopes: set[str],
    ) -> dict[str, Any] | None: ...

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
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class RuntimeConfig:
    stack_root: Path
    runtime_root: Path
    sqlite_path: Path
    current_path: Path
    qdrant_url: str
    qdrant_alias: str
    embedding_url: str
    neo4j_url: str
    neo4j_database: str
    http_timeout: float
    sqlite_timeout: float

    @classmethod
    def discover(cls, stack_root: str | Path | None = None) -> "RuntimeConfig":
        raw_root = (
            Path(
                stack_root
                or os.environ.get("AOA_STACK_ROOT")
                or os.environ.get("AOA_ABYSS_STACK_ROOT")
                or "/srv/AbyssOS/abyss-stack"
            )
            .expanduser()
            .resolve()
        )
        root = raw_root.parent if raw_root.name == "Configs" else raw_root
        runtime_root = root / "Knowledge" / "kag" / "repo-self"
        return cls(
            stack_root=root,
            runtime_root=runtime_root,
            sqlite_path=runtime_root / "exact" / "repo-self.sqlite3",
            current_path=runtime_root / "current.json",
            qdrant_url=os.environ.get("AOA_KAG_QDRANT_URL", "http://127.0.0.1:6333"),
            qdrant_alias=os.environ.get("AOA_KAG_QDRANT_ALIAS", vector.DEFAULT_ALIAS),
            embedding_url=os.environ.get(
                "AOA_KAG_EMBEDDING_URL", "http://127.0.0.1:5403"
            ),
            neo4j_url=os.environ.get("AOA_KAG_NEO4J_HTTP_URL", "http://127.0.0.1:7474"),
            neo4j_database=os.environ.get("AOA_KAG_NEO4J_DATABASE", "neo4j"),
            http_timeout=float(os.environ.get("AOA_KAG_QUERY_HTTP_TIMEOUT", "15")),
            sqlite_timeout=float(os.environ.get("AOA_KAG_QUERY_SQLITE_TIMEOUT", "5")),
        )


def _json_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _dotenv_values(path: Path, keys: set[str]) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in keys:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _neo4j_headers(stack_root: Path) -> dict[str, str]:
    user = os.environ.get("AOA_KAG_NEO4J_USER") or os.environ.get("AOA_RAG_NEO4J_USER")
    password = os.environ.get("AOA_KAG_NEO4J_PASSWORD") or os.environ.get(
        "AOA_RAG_NEO4J_PASSWORD"
    )
    raw = os.environ.get("AOA_KAG_NEO4J_AUTH") or os.environ.get("NEO4J_AUTH")
    if not raw and (not user or not password):
        deployed = _dotenv_values(
            stack_root / "Secrets" / "Configs" / "stack.env",
            {"NEO4J_AUTH", "AOA_RAG_NEO4J_USER", "AOA_RAG_NEO4J_PASSWORD"},
        )
        user = user or deployed.get("AOA_RAG_NEO4J_USER")
        password = password or deployed.get("AOA_RAG_NEO4J_PASSWORD")
        raw = deployed.get("NEO4J_AUTH")
    if (not user or not password) and raw and raw.lower() != "none" and "/" in raw:
        user, password = raw.split("/", 1)
    if not user or not password:
        raise RuntimeError("Neo4j credentials are unavailable")
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _client_headers(env_name: str) -> dict[str, str]:
    value = os.environ.get(env_name)
    return {"api-key": value} if value else {}


def _qualified_owner(record_id: str) -> str | None:
    parts = record_id.split(":", 3)
    return parts[1] if len(parts) == 4 and parts[0] == "aoa" else None


def _resource_uri(
    resource_class: str, identifier: str, owner: str | None = None
) -> str:
    segments = [resource_class]
    if owner:
        segments.append(quote(owner, safe=""))
    segments.append(quote(identifier, safe=""))
    return "aoa-kag://" + "/".join(segments)


def _request_digest(payload: dict[str, Any]) -> str:
    material = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _encode_cursor(offset: int, request_digest: str) -> str:
    raw = json.dumps(
        {"v": 1, "offset": offset, "request_digest": request_digest},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str | None, request_digest: str) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid KAG cursor") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("v") != 1
        or payload.get("request_digest") != request_digest
        or not isinstance(payload.get("offset"), int)
        or payload["offset"] < 0
    ):
        raise ValueError("KAG cursor does not match this request")
    return int(payload["offset"])


class KagApplication:
    """Storage-neutral KAG operations consumed by MCP and local clients."""

    def __init__(
        self,
        *,
        config: RuntimeConfig | None = None,
        canonical: CanonicalKag | None = None,
        access_scopes: Sequence[str] = ("public",),
    ) -> None:
        self.config = config or RuntimeConfig.discover()
        self.canonical = canonical
        self.access_scopes = tuple(dict.fromkeys(access_scopes))
        self._traces: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._trace_lock = threading.Lock()

    @contextmanager
    def _exact(self) -> Iterator[sqlite3.Connection]:
        if not self.config.sqlite_path.is_file():
            raise RuntimeError("exact projection is unavailable")
        uri = f"file:{quote(self.config.sqlite_path.as_posix())}?mode=ro"
        connection = sqlite3.connect(
            uri,
            uri=True,
            timeout=self.config.sqlite_timeout,
        )
        connection.row_factory = sqlite3.Row
        deadline = time.monotonic() + self.config.sqlite_timeout
        connection.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0,
            10_000,
        )
        try:
            yield connection
        finally:
            connection.close()

    def _current(self) -> dict[str, Any]:
        try:
            return _json_file(self.config.current_path)
        except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError):
            return {}

    def _projection(self) -> dict[str, Any]:
        current = self._current()
        identity = current.get("projection_identity")
        digest = (
            str(identity.get("content_digest") or "")
            if isinstance(identity, dict)
            else ""
        )
        targets = (
            current.get("targets") if isinstance(current.get("targets"), dict) else {}
        )
        exact_state = "missing"
        exact_digest = ""
        if self.config.sqlite_path.is_file():
            try:
                with self._exact() as connection:
                    metadata = exact.projection_metadata(connection)
                exact_digest = metadata.get("projection_digest", "")
                exact_state = (
                    "current" if digest and exact_digest == digest else "mismatched"
                )
            except (RuntimeError, sqlite3.Error):
                exact_state = "damaged"
        target_states = {
            name: {
                "state": (
                    exact_state
                    if name == "exact"
                    else str((targets.get(name) or {}).get("status") or "missing")
                ),
                "completed_at": (targets.get(name) or {}).get("completed_at"),
            }
            for name in ("exact", "vector", "graph", "retrieval_eval")
        }
        return {
            "digest": digest or exact_digest,
            "bundle_digest": str(
                (current.get("bundle_identity") or {}).get("content_digest") or ""
            ),
            "federation_digest": str(
                (current.get("federation_identity") or {}).get("content_digest") or ""
            ),
            "updated_at": current.get("updated_at"),
            "targets": target_states,
        }

    def _owner_freshness(
        self,
        repo: str,
        *,
        runtime_digest: str | None = None,
    ) -> dict[str, Any]:
        if runtime_digest is None:
            try:
                with self._exact() as connection:
                    owner = exact.read_owner(connection, repo)
                runtime_digest = (
                    str(owner.get("source_index_digest"))
                    if isinstance(owner, dict)
                    else ""
                )
            except (RuntimeError, sqlite3.Error):
                runtime_digest = ""
        canonical_error = ""
        try:
            canonical_digest = (
                self.canonical.owner_digest(repo) if self.canonical else None
            )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            canonical_digest = None
            canonical_error = type(exc).__name__
        if canonical_digest and runtime_digest:
            state = "current" if canonical_digest == runtime_digest else "stale"
        elif canonical_digest:
            state = "canonical_only"
        elif runtime_digest:
            state = "source_unavailable"
        else:
            state = "unknown"
        result = {
            "state": state,
            "runtime_source_digest": runtime_digest or "",
            "canonical_source_digest": canonical_digest or "",
        }
        if canonical_error:
            result["canonical_error"] = canonical_error
        return result

    def _record_owner(self, record_id: str) -> str | None:
        if self.canonical:
            try:
                resolved = self.canonical.resolve_owner(record_id)
            except (KeyError, OSError, RuntimeError, TypeError, ValueError):
                resolved = None
            if resolved:
                return resolved
        return _qualified_owner(record_id)

    def _trace(self, payload: dict[str, Any]) -> str:
        trace_id = str(uuid.uuid4())
        with self._trace_lock:
            self._traces[trace_id] = payload
            self._traces.move_to_end(trace_id)
            while len(self._traces) > 128:
                self._traces.popitem(last=False)
        return trace_id

    def _trace_value(self, trace_id: str) -> dict[str, Any] | None:
        with self._trace_lock:
            value = self._traces.get(trace_id)
            if value is not None:
                self._traces.move_to_end(trace_id)
                return json.loads(json.dumps(value))
        return None

    def discover(
        self,
        *,
        owner: str | None = None,
        detail: str = "compact",
    ) -> dict[str, Any]:
        if detail not in DETAIL_LEVELS:
            raise ValueError(f"unsupported detail level: {detail}")
        projection = self._projection()
        owners: list[dict[str, Any]] = []
        classes: dict[str, set[str]] = defaultdict(set)
        document_classes: set[str] = set()
        canonical_owner_names: set[str] = set()
        if self.canonical:
            try:
                canonical_owner_names = set(self.canonical.owner_names())
            except (KeyError, OSError, RuntimeError, TypeError, ValueError):
                canonical_owner_names = set()
        try:
            with self._exact() as connection:
                runtime_owners = exact.owner_records(connection)
                for _, node_class, kind in exact.record_kinds(
                    connection,
                    repo=owner,
                ):
                    classes[node_class].add(kind)
                for row in connection.execute(
                    "SELECT DISTINCT node_class FROM documents "
                    + ("WHERE repo=? " if owner else "")
                    + "ORDER BY node_class",
                    (owner,) if owner else (),
                ):
                    document_classes.add(str(row[0]))
        except (RuntimeError, sqlite3.Error):
            runtime_owners = []
        for packet in runtime_owners:
            repo_packet = (
                packet.get("repo") if isinstance(packet.get("repo"), dict) else {}
            )
            repo = str(repo_packet.get("name") or "")
            if not repo or (owner and repo != owner):
                continue
            row = {
                "repo": repo,
                "manifest_uri": f"aoa-kag://owners/{quote(repo, safe='')}/manifest",
            }
            if owner or detail != "compact":
                row.update(
                    {
                        "namespace": repo_packet.get("namespace"),
                        "owner_type": repo_packet.get("owner_type"),
                        "record_counts": packet.get("node_counts", {}),
                        "relation_count": packet.get("relation_count", 0),
                        "runtime_source_digest": packet.get("source_index_digest"),
                    }
                )
            if owner or detail == "full":
                row["freshness"] = self._owner_freshness(
                    repo,
                    runtime_digest=str(packet.get("source_index_digest") or ""),
                )
            owners.append(row)
        if not owners and self.canonical:
            for repo in sorted(canonical_owner_names):
                if not owner or owner == repo:
                    row = {
                        "repo": repo,
                        "manifest_uri": f"aoa-kag://owners/{quote(repo, safe='')}/manifest",
                    }
                    if owner or detail != "compact":
                        row["freshness"] = self._owner_freshness(repo)
                    owners.append(row)
        canonical_ready = bool(owner and owner in canonical_owner_names)
        if canonical_ready and self.canonical:
            try:
                canonical_capabilities = self.canonical.discover_owner(owner)
            except (KeyError, OSError, RuntimeError, TypeError, ValueError):
                canonical_capabilities = None
            if isinstance(canonical_capabilities, dict):
                kind_counts = canonical_capabilities.get("kind_counts")
                if isinstance(kind_counts, dict):
                    for node_class, kinds in kind_counts.items():
                        if isinstance(kinds, dict):
                            classes[str(node_class)].update(str(kind) for kind in kinds)
        record_classes = sorted(classes)
        graph_classes = [item for item in record_classes if item != "relation"]
        strategy_classes = {
            "auto": record_classes,
            "exact": record_classes,
            "lexical": record_classes,
            "semantic": sorted(document_classes),
            "hybrid": record_classes,
            "graph": graph_classes,
        }
        payload: dict[str, Any] = {
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "owners": owners,
            "record_classes": record_classes,
            "strategies": [
                {
                    "name": name,
                    "available": self._strategy_available(
                        name,
                        projection,
                        canonical_ready=canonical_ready,
                    ),
                    "record_classes": strategy_classes[name],
                }
                for name in SEARCH_STRATEGIES
            ],
            "detail_levels": list(DETAIL_LEVELS),
            "access_scopes": list(self.access_scopes),
            "limits": {
                "page_size": MAX_PAGE_SIZE,
                "traversal_depth": MAX_TRAVERSAL_DEPTH,
                "full_text_chars": MAX_FULL_TEXT_CHARS,
            },
            "resource_templates": [
                "aoa-kag://owners/{repo}/manifest",
                "aoa-kag://records/{qualified_id}",
                "aoa-kag://documents/{document_id}",
                "aoa-kag://sources/{repo}/{document_id}",
                "aoa-kag://anchors/{anchor_id}",
                "aoa-kag://evidence/{trace_id}",
                "aoa-kag://schemas/{name}",
                "aoa-kag://projections/{digest}",
            ],
            "projection": projection,
        }
        if detail == "full":
            payload["kinds"] = {
                node_class: sorted(kinds)
                for node_class, kinds in sorted(classes.items())
            }
        if detail != "compact":
            payload["filters"] = [
                "owner",
                "record_class",
                "kind",
                "document_role",
                "surface_state",
                "path",
                "path_prefix",
                "access_scope",
            ]
        return payload

    @staticmethod
    def _strategy_available(
        strategy: str,
        projection: dict[str, Any],
        *,
        canonical_ready: bool = False,
    ) -> bool:
        states = projection["targets"]
        exact_ready = states["exact"]["state"] in {"current", "mismatched"}
        vector_ready = states["vector"]["state"] == "current"
        graph_ready = states["graph"]["state"] == "current"
        return {
            "auto": exact_ready or canonical_ready,
            "exact": exact_ready or canonical_ready,
            "lexical": exact_ready or canonical_ready,
            "semantic": vector_ready,
            "hybrid": exact_ready or vector_ready or canonical_ready,
            "graph": graph_ready or exact_ready or canonical_ready,
        }[strategy]

    @staticmethod
    def _auto_strategy(query: str, projection: dict[str, Any]) -> str:
        stripped = query.strip()
        path_like = "/" in stripped or stripped.endswith(
            (".md", ".py", ".json", ".yaml", ".yml", ".toml", ".sh")
        )
        if stripped.startswith("aoa:") or path_like:
            return "exact"
        if KagApplication._strategy_available("semantic", projection):
            return "hybrid"
        return "lexical"

    @staticmethod
    def _distinct_record_hits(
        hits: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        distinct: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in hits:
            identifier = str(
                hit.get("id") or hit.get("node_id") or hit.get("document_id") or ""
            )
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            distinct.append(hit)
        return distinct

    @staticmethod
    def _merge_exact_hits(
        documents: list[dict[str, Any]],
        records: list[dict[str, Any]],
        *,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        documents = KagApplication._distinct_record_hits(documents)
        document_nodes = {str(item.get("id") or "") for item in documents}
        records = KagApplication._distinct_record_hits(
            [
                item
                for item in records
                if str(item.get("id") or "") not in document_nodes
            ]
        )
        merged: list[dict[str, Any]] = []
        for rank in range(max(len(documents), len(records))):
            if rank < len(documents):
                merged.append(documents[rank])
            if rank < len(records):
                merged.append(records[rank])
        return merged[offset : offset + limit]

    @staticmethod
    def _merge_lexical_hits(
        documents: list[dict[str, Any]],
        records: list[dict[str, Any]],
        *,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        documents = KagApplication._distinct_record_hits(documents)
        document_nodes = {str(item.get("id") or "") for item in documents}
        records = KagApplication._distinct_record_hits(
            [
                item
                for item in records
                if str(item.get("id") or "") not in document_nodes
            ]
        )
        candidates: list[tuple[float, str, dict[str, Any]]] = []
        for lane, hits in (("document", documents), ("record", records)):
            for rank, item in enumerate(hits, 1):
                identifier = str(item.get("id") or "")
                if not identifier:
                    continue
                value = dict(item)
                value["score"] = 1.0 / (60 + rank)
                candidates.append((value["score"], f"{lane}:{identifier}", value))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in candidates[offset : offset + limit]]

    def _runtime_hits(
        self,
        query: str,
        *,
        strategy: str,
        owner: str | None,
        record_class: str | None,
        kind: str | None,
        document_role: str | None,
        surface_state: str | None,
        path: str | None,
        path_prefix: str | None,
        detail: str,
        offset: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        routes: list[dict[str, Any]] = []
        if strategy in {"exact", "lexical"}:
            with self._exact() as connection:
                lane_limit = offset + limit + 16
                if strategy == "exact":
                    documents, document_latency = exact.search_documents_exact(
                        connection,
                        query,
                        repo=owner,
                        node_class=record_class,
                        kind=kind,
                        document_role=document_role,
                        surface_state=surface_state,
                        path=path,
                        path_prefix=path_prefix,
                        access_scopes=self.access_scopes,
                        detail=detail,
                        offset=0,
                        limit=lane_limit,
                    )
                    records, record_latency = exact.search_records_exact(
                        connection,
                        query,
                        repo=owner,
                        node_class=record_class,
                        kind=kind,
                        document_role=document_role,
                        surface_state=surface_state,
                        path=path,
                        path_prefix=path_prefix,
                        access_scopes=self.access_scopes,
                        detail=detail,
                        offset=0,
                        limit=lane_limit,
                    )
                    hits = self._merge_exact_hits(
                        documents,
                        records,
                        offset=offset,
                        limit=limit,
                    )
                else:
                    documents, document_latency = exact.search_documents_lexical(
                        connection,
                        query,
                        repo=owner,
                        node_class=record_class,
                        kind=kind,
                        document_role=document_role,
                        surface_state=surface_state,
                        path=path,
                        path_prefix=path_prefix,
                        access_scopes=self.access_scopes,
                        operator="OR",
                        detail=detail,
                        offset=0,
                        limit=lane_limit,
                    )
                    records, record_latency = exact.search_records_lexical(
                        connection,
                        query,
                        repo=owner,
                        node_class=record_class,
                        kind=kind,
                        document_role=document_role,
                        surface_state=surface_state,
                        path=path,
                        path_prefix=path_prefix,
                        access_scopes=self.access_scopes,
                        operator="OR",
                        detail=detail,
                        offset=0,
                        limit=lane_limit,
                    )
                    hits = self._merge_lexical_hits(
                        documents,
                        records,
                        offset=offset,
                        limit=limit,
                    )
            routes.extend(
                (
                    {
                        "adapter": f"sqlite-document-{strategy}",
                        "latency_ms": document_latency,
                    },
                    {
                        "adapter": f"sqlite-record-{strategy}",
                        "latency_ms": record_latency,
                    },
                )
            )
            return hits, routes
        if strategy == "semantic":
            current = self._current()
            vector_result = ((current.get("targets") or {}).get("vector") or {}).get(
                "result"
            ) or {}
            profile = vector_result.get("embedding_profile")
            if not isinstance(profile, dict):
                raise RuntimeError("vector embedding profile is unavailable")
            qdrant = JsonHttpClient(
                self.config.qdrant_url,
                headers=_client_headers("AOA_KAG_QDRANT_API_KEY"),
                timeout=self.config.http_timeout,
            )
            embeddings = JsonHttpClient(
                self.config.embedding_url,
                headers=_client_headers("AOA_KAG_EMBEDDING_API_KEY"),
                timeout=self.config.http_timeout,
            )
            points, latency = vector.search(
                query,
                qdrant=qdrant,
                embeddings=embeddings,
                profile=profile,
                alias=self.config.qdrant_alias,
                repo=owner,
                node_class=record_class,
                kind=kind,
                document_role=document_role,
                surface_state=surface_state,
                path=path,
                access_scopes=self.access_scopes,
                offset=0,
                limit=offset + limit + 16,
            )
            hits = []
            for point in points:
                payload = point.get("payload")
                if not isinstance(payload, dict):
                    continue
                payload_path = str(payload.get("path") or "")
                if path_prefix and not payload_path.startswith(path_prefix):
                    continue
                if not document_role and (
                    "retrieval-eval." in payload_path.casefold()
                    or "retrieval_eval." in payload_path.casefold()
                    or "/fixtures/" in f"/{payload_path.casefold()}/"
                ):
                    continue
                normalized = dict(payload)
                normalized["document_id"] = str(payload.get("id") or "")
                normalized["id"] = str(
                    payload.get("node_id") or payload.get("id") or ""
                )
                normalized["semantic_score"] = float(point.get("score") or 0.0)
                if detail == "compact":
                    normalized.pop("text", None)
                elif detail == "summary" and "text" in normalized:
                    normalized["snippet"] = str(normalized.pop("text"))[:480]
                hits.append(normalized)
            hits.sort(
                key=lambda item: (
                    -float(item.get("semantic_score") or 0.0),
                    str(item.get("document_id") or ""),
                )
            )
            hits = self._distinct_record_hits(hits)[offset : offset + limit]
            routes.append({"adapter": "qdrant-vector", "latency_ms": latency})
            return hits, routes
        raise ValueError(f"unsupported runtime document strategy: {strategy}")

    def _canonical_hits(
        self,
        query: str,
        *,
        strategy: str,
        owner: str,
        record_class: str | None,
        kind: str | None,
        document_role: str | None,
        surface_state: str | None,
        path_prefix: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not self.canonical:
            return []
        canonical_strategy = {
            "semantic": "hybrid",
            "auto": "hybrid",
        }.get(strategy, strategy)
        if canonical_strategy not in {"exact", "lexical", "graph", "hybrid"}:
            canonical_strategy = "hybrid"
        return self.canonical.search_owner(
            owner,
            query,
            strategy=canonical_strategy,
            record_class=record_class,
            kind=kind,
            document_role=document_role,
            surface_state=surface_state,
            path_prefix=path_prefix,
            access_scopes=set(self.access_scopes),
            limit=limit,
        )

    @staticmethod
    def _hybrid(
        lexical: list[dict[str, Any]],
        semantic: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        scores: dict[str, float] = defaultdict(float)
        components: dict[str, dict[str, float]] = defaultdict(dict)
        values: dict[str, dict[str, Any]] = {}
        for lane, ranking in (("lexical", lexical), ("semantic", semantic)):
            seen: set[str] = set()
            for rank, hit in enumerate(ranking, 1):
                identifier = str(
                    hit.get("id") or hit.get("node_id") or hit.get("document_id") or ""
                )
                if not identifier or identifier in seen:
                    continue
                seen.add(identifier)
                contribution = 1.0 / (60 + rank)
                scores[identifier] += contribution
                components[identifier][lane] = contribution
                values.setdefault(identifier, hit)
        ranked = sorted(scores, key=lambda item: (-scores[item], item))[:limit]
        return [
            {
                **values[identifier],
                "hybrid_score": scores[identifier],
                "hybrid_components": components[identifier],
            }
            for identifier in ranked
        ]

    def _normalize_hit(
        self,
        hit: dict[str, Any],
        *,
        strategy: str,
        projection: dict[str, Any],
        freshness: dict[str, Any],
        detail: str,
    ) -> dict[str, Any]:
        identifier = str(hit.get("id") or hit.get("node_id") or "")
        document_id = str(hit.get("document_id") or "")
        owner = str(hit.get("repo") or self._record_owner(identifier) or "")
        access = hit.get("access")
        if not isinstance(access, dict):
            access = {"scope": hit.get("access_scope", "public")}
        profiles = hit.get("profiles") if isinstance(hit.get("profiles"), dict) else {}
        sources = hit.get("sources") if isinstance(hit.get("sources"), list) else []
        primary_source = sources[0] if sources and isinstance(sources[0], dict) else {}
        provenance = (
            hit.get("provenance")
            or profiles.get("provenance")
            or {"ref": hit.get("provenance_ref", "")}
        )
        trust = (
            hit.get("trust")
            or profiles.get("trust")
            or {"ref": hit.get("trust_ref", "")}
        )
        temporal = (
            hit.get("temporal")
            or profiles.get("temporal")
            or {"ref": hit.get("temporal_ref", "")}
        )
        evidence_path = (
            hit.get("evidence_path")
            if isinstance(hit.get("evidence_path"), dict)
            else {}
        )
        evidence_relations = evidence_path.get("relations")
        first_relation = (
            evidence_relations[0]
            if isinstance(evidence_relations, list)
            and evidence_relations
            and isinstance(evidence_relations[0], dict)
            else {}
        )
        if not provenance.get("ref") and first_relation.get("provenance_ref"):
            provenance = {"ref": first_relation["provenance_ref"]}
        if not trust.get("ref") and first_relation.get("trust_ref"):
            trust = {
                "ref": first_relation["trust_ref"],
                "confidence": first_relation.get("confidence"),
            }
        if not temporal.get("ref") and first_relation.get("temporal_ref"):
            temporal = {"ref": first_relation["temporal_ref"]}
        if "hybrid_score" in hit:
            total = float(hit["hybrid_score"])
        elif "semantic_score" in hit:
            total = float(hit["semantic_score"])
        elif "score" in hit:
            total = float(hit["score"])
        else:
            total = 1.0
        links = {
            "record": _resource_uri("records", identifier),
            "projection": _resource_uri("projections", projection["digest"]),
        }
        if document_id:
            links["document"] = _resource_uri("documents", document_id)
            links["source"] = _resource_uri("sources", document_id, owner)
        anchors = [str(item) for item in hit.get("anchor_ids", [])]
        if anchors:
            links["anchors"] = [_resource_uri("anchors", item) for item in anchors]
        result = {
            "qualified_id": identifier,
            "owner": {
                "repo": owner,
                "namespace": hit.get("namespace") or f"aoa:{owner}",
            },
            "record_class": hit.get("node_class"),
            "kind": hit.get("kind"),
            "label": hit.get("label"),
            "path": hit.get("path"),
            "document_role": hit.get("document_role") or "none",
            "surface_state": hit.get("surface_state") or "authored_source",
            "locator": hit.get("locator", {}),
            "source_record_ids": hit.get("source_record_ids", []),
            "source_anchors": anchors,
            "provenance": provenance,
            "trust": trust,
            "temporal": temporal,
            "freshness": freshness,
            "abi": hit.get("abi") or primary_source.get("abi") or {},
            "signs": hit.get("signs") or primary_source.get("signs") or {},
            "access": access,
            "strategy": strategy,
            "score": {
                "total": round(total, 8),
                "lexical_rank": hit.get("lexical_rank"),
                "semantic": hit.get("semantic_score"),
                "hybrid": hit.get("hybrid_components", {}),
            },
            "projection_digest": projection["digest"],
            "resources": links,
            "detail": detail,
        }
        inspection = _content_inspection(
            {
                "label": hit.get("label"),
                "path": hit.get("path"),
                "snippet": hit.get("snippet"),
                "text": hit.get("text"),
            }
        )
        if inspection:
            result["content_inspection"] = inspection
        if detail == "summary" and hit.get("snippet") is not None:
            result["snippet"] = hit["snippet"]
        if detail == "full":
            if hit.get("text") is not None:
                text = str(hit["text"])
                result["text"] = text[:MAX_FULL_TEXT_CHARS]
                result["text_chars"] = len(text)
                result["text_truncated"] = len(text) > MAX_FULL_TEXT_CHARS
            if hit.get("record") is not None:
                result["record"] = hit["record"]
            if hit.get("sources") is not None:
                result["sources"] = hit["sources"]
        if hit.get("evidence_path") is not None:
            result["evidence_path"] = hit["evidence_path"]
        return result

    def search(
        self,
        query: str,
        *,
        strategy: str = "auto",
        owner: str | None = None,
        record_class: str | None = None,
        kind: str | None = None,
        document_role: str | None = None,
        surface_state: str | None = None,
        path: str | None = None,
        path_prefix: str | None = None,
        detail: str = "compact",
        limit: int = 10,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("query must be non-empty")
        if strategy not in SEARCH_STRATEGIES:
            raise ValueError(f"unsupported search strategy: {strategy}")
        if detail not in DETAIL_LEVELS:
            raise ValueError(f"unsupported detail level: {detail}")
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be from 1 through {MAX_PAGE_SIZE}")
        request = {
            "query": query,
            "strategy": strategy,
            "owner": owner,
            "record_class": record_class,
            "kind": kind,
            "document_role": document_role,
            "surface_state": surface_state,
            "path": path,
            "path_prefix": path_prefix,
            "detail": detail,
            "limit": limit,
        }
        request_digest = _request_digest(request)
        offset = _decode_cursor(cursor, request_digest)
        projection = self._projection()
        used_strategy = (
            self._auto_strategy(query, projection) if strategy == "auto" else strategy
        )
        degradation: list[dict[str, Any]] = []
        if (
            used_strategy in {"exact", "lexical", "hybrid", "graph"}
            and projection["targets"]["exact"]["state"] == "mismatched"
        ):
            degradation.append(
                {
                    "target": "runtime-projection-state",
                    "state": "mismatched",
                    "fallback": "sqlite-self-described-projection",
                }
            )
        routes: list[dict[str, Any]] = []
        owner_freshness = self._owner_freshness(owner) if owner else {"state": "mixed"}
        fetch_limit = limit + 1
        raw_hits: list[dict[str, Any]] = []

        use_canonical = bool(
            owner
            and self.canonical
            and owner_freshness["state"] in {"stale", "canonical_only"}
            and used_strategy in {"exact", "lexical"}
        )
        if (
            owner
            and owner_freshness["state"] == "stale"
            and used_strategy in {"semantic", "hybrid", "graph"}
        ):
            degradation.append(
                {
                    "target": f"{used_strategy}-owner-snapshot",
                    "state": "stale",
                    "fallback": "runtime-stale-with-provenance",
                }
            )
        if use_canonical:
            started = time.perf_counter()
            try:
                raw_hits = self._canonical_hits(
                    query,
                    strategy=used_strategy,
                    owner=owner,
                    record_class=record_class,
                    kind=kind,
                    document_role=document_role,
                    surface_state=surface_state,
                    path_prefix=path_prefix or path or "",
                    limit=offset + fetch_limit,
                )[offset:]
                routes.append(
                    {
                        "adapter": "canonical-repo-local",
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
                degradation.append(
                    {
                        "target": "runtime-owner-snapshot",
                        "state": owner_freshness["state"],
                        "fallback": "canonical-repo-local",
                    }
                )
            except (KeyError, OSError, RuntimeError, ValueError) as exc:
                try:
                    raw_hits, runtime_routes = self._runtime_hits(
                        query,
                        strategy=used_strategy,
                        owner=owner,
                        record_class=record_class,
                        kind=kind,
                        document_role=document_role,
                        surface_state=surface_state,
                        path=path,
                        path_prefix=path_prefix,
                        detail=detail,
                        offset=offset,
                        limit=fetch_limit,
                    )
                    routes.extend(runtime_routes)
                    canonical_fallback = "runtime-stale-with-provenance"
                except (RuntimeError, sqlite3.Error, OSError) as runtime_exc:
                    raw_hits = []
                    canonical_fallback = "empty-bounded-result"
                    degradation.append(
                        {
                            "target": "runtime",
                            "state": "unavailable",
                            "fallback": canonical_fallback,
                            "reason": type(runtime_exc).__name__,
                        }
                    )
                degradation.append(
                    {
                        "target": "canonical-owner-source",
                        "state": "unavailable",
                        "fallback": canonical_fallback,
                        "reason": type(exc).__name__,
                    }
                )
        else:
            try:
                if used_strategy == "hybrid":
                    lane_limit = offset + fetch_limit + 20
                    lexical, lexical_routes = self._runtime_hits(
                        query,
                        strategy="lexical",
                        owner=owner,
                        record_class=record_class,
                        kind=kind,
                        document_role=document_role,
                        surface_state=surface_state,
                        path=path,
                        path_prefix=path_prefix,
                        detail=detail,
                        offset=0,
                        limit=lane_limit,
                    )
                    routes.extend(lexical_routes)
                    try:
                        semantic, semantic_routes = self._runtime_hits(
                            query,
                            strategy="semantic",
                            owner=owner,
                            record_class=record_class,
                            kind=kind,
                            document_role=document_role,
                            surface_state=surface_state,
                            path=path,
                            path_prefix=path_prefix,
                            detail=detail,
                            offset=0,
                            limit=lane_limit,
                        )
                        routes.extend(semantic_routes)
                    except (RuntimeError, OSError, ValueError) as exc:
                        semantic = []
                        degradation.append(
                            {
                                "target": "vector",
                                "state": "unavailable",
                                "fallback": "lexical",
                                "reason": type(exc).__name__,
                            }
                        )
                    raw_hits = self._hybrid(
                        lexical,
                        semantic,
                        limit=offset + fetch_limit,
                    )[offset:]
                elif used_strategy == "graph":
                    lexical, lexical_routes = self._runtime_hits(
                        query,
                        strategy="lexical",
                        owner=owner,
                        record_class=record_class,
                        kind=kind,
                        document_role=document_role,
                        surface_state=surface_state,
                        path=path,
                        path_prefix=path_prefix,
                        detail="compact",
                        offset=0,
                        limit=8,
                    )
                    routes.extend(lexical_routes)
                    seed_ids = list(
                        dict.fromkeys(str(hit.get("id") or "") for hit in lexical)
                    )
                    traversal = self.traverse(
                        seed_ids,
                        owner=owner,
                        query=query,
                        max_depth=2,
                        detail=detail,
                        limit=offset + fetch_limit,
                    )
                    raw_hits = [dict(item) for item in traversal["results"]][offset:]
                    routes.extend(traversal["route"]["adapters"])
                    degradation.extend(traversal["route"]["degradation"])
                else:
                    raw_hits, runtime_routes = self._runtime_hits(
                        query,
                        strategy=used_strategy,
                        owner=owner,
                        record_class=record_class,
                        kind=kind,
                        document_role=document_role,
                        surface_state=surface_state,
                        path=path,
                        path_prefix=path_prefix,
                        detail=detail,
                        offset=offset,
                        limit=fetch_limit,
                    )
                    routes.extend(runtime_routes)
            except (RuntimeError, sqlite3.Error, OSError) as exc:
                if (
                    owner
                    and self.canonical
                    and used_strategy
                    in {
                        "exact",
                        "lexical",
                        "graph",
                        "hybrid",
                    }
                ):
                    started = time.perf_counter()
                    raw_hits = self._canonical_hits(
                        query,
                        strategy=used_strategy,
                        owner=owner,
                        record_class=record_class,
                        kind=kind,
                        document_role=document_role,
                        surface_state=surface_state,
                        path_prefix=path_prefix or path or "",
                        limit=offset + fetch_limit,
                    )[offset:]
                    routes.append(
                        {
                            "adapter": "canonical-repo-local",
                            "latency_ms": (time.perf_counter() - started) * 1000,
                        }
                    )
                    degradation.append(
                        {
                            "target": "runtime",
                            "state": "unavailable",
                            "fallback": "canonical-repo-local",
                            "reason": type(exc).__name__,
                        }
                    )
                else:
                    raw_hits = []
                    degradation.append(
                        {
                            "target": "runtime",
                            "state": "unavailable",
                            "fallback": "empty-bounded-result",
                            "reason": type(exc).__name__,
                        }
                    )

        has_more = len(raw_hits) > limit
        raw_hits = raw_hits[:limit]
        normalized: list[dict[str, Any]] = []
        for hit in raw_hits:
            repo = str(
                hit.get("repo")
                or self._record_owner(str(hit.get("id") or ""))
                or owner
                or ""
            )
            freshness = self._owner_freshness(repo) if repo else owner_freshness
            if "qualified_id" in hit:
                normalized.append(hit)
            else:
                normalized.append(
                    self._normalize_hit(
                        hit,
                        strategy=used_strategy,
                        projection=projection,
                        freshness=freshness,
                        detail=detail,
                    )
                )
        seen_degradation = {(item["target"], item["state"]) for item in degradation}
        for item in normalized:
            freshness = item.get("freshness")
            state = freshness.get("state") if isinstance(freshness, dict) else None
            repo = str((item.get("owner") or {}).get("repo") or "")
            key = (f"owner:{repo}", str(state))
            if (
                state in {"stale", "canonical_only", "source_unavailable", "unknown"}
                and key not in seen_degradation
            ):
                degradation.append(
                    {
                        "target": key[0],
                        "state": key[1],
                        "fallback": "result-level-freshness",
                    }
                )
                seen_degradation.add(key)
        status = "degraded" if degradation else ("empty" if not normalized else "ok")
        trace_payload = {
            "operation": "search",
            "request": request,
            "route": {
                "requested_strategy": strategy,
                "used_strategy": used_strategy,
                "adapters": routes,
                "degradation": degradation,
            },
            "projection": projection,
            "result_ids": [item["qualified_id"] for item in normalized],
        }
        trace_id = self._trace(trace_payload)
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "operation": "search",
            "status": status,
            "trace_id": trace_id,
            "query": request,
            "route": trace_payload["route"],
            "projection": projection,
            "page": {
                "limit": limit,
                "offset": offset,
                "count": len(normalized),
                "next_cursor": (
                    _encode_cursor(offset + len(normalized), request_digest)
                    if has_more
                    else None
                ),
            },
            "results": normalized,
            "resources": {
                "evidence": _resource_uri("evidence", trace_id),
                "projection": _resource_uri("projections", projection["digest"]),
            },
        }

    def read(self, uri: str, *, detail: str = "full") -> dict[str, Any]:
        if detail not in DETAIL_LEVELS:
            raise ValueError(f"unsupported detail level: {detail}")
        parsed = urlparse(uri)
        if parsed.scheme != "aoa-kag" or not parsed.netloc:
            raise ValueError("unsupported KAG resource URI")
        resource_class = parsed.netloc
        parts = [unquote(item) for item in parsed.path.split("/") if item]
        projection = self._projection()
        payload: Any = None
        route = "runtime-exact"
        degradation: list[dict[str, Any]] = []
        if resource_class == "owners" and len(parts) == 2 and parts[1] == "manifest":
            payload = (
                self.canonical.owner_manifest(parts[0]) if self.canonical else None
            )
            route = "canonical-repo-local"
        elif resource_class in {"records", "anchors"} and len(parts) == 1:
            record_id = parts[0]
            owner = self._record_owner(record_id)
            freshness = self._owner_freshness(owner) if owner else {"state": "unknown"}
            prefer_canonical = bool(
                self.canonical
                and owner
                and (
                    detail == "full"
                    or freshness["state"] in {"stale", "canonical_only"}
                )
            )
            if prefer_canonical:
                try:
                    payload = self.canonical.read_record(
                        owner, record_id, access_scopes=set(self.access_scopes)
                    )
                    route = "canonical-repo-local"
                except (KeyError, OSError, RuntimeError, ValueError) as exc:
                    payload = None
                    degradation.append(
                        {
                            "target": "canonical-owner-source",
                            "state": "unavailable",
                            "fallback": "runtime-stale-with-provenance",
                            "reason": type(exc).__name__,
                        }
                    )
                if payload is None:
                    try:
                        with self._exact() as connection:
                            node = exact.read_record(
                                connection,
                                record_id,
                                access_scopes=self.access_scopes,
                            )
                            documents = exact.documents_for_node(
                                connection,
                                record_id,
                                access_scopes=self.access_scopes,
                                detail="summary" if detail == "full" else detail,
                                limit=MAX_PAGE_SIZE,
                            )
                            document_count = exact.document_count_for_node(
                                connection,
                                record_id,
                                access_scopes=self.access_scopes,
                            )
                        payload = (
                            {
                                "record": node,
                                "documents": documents,
                                "document_count": document_count,
                            }
                            if node
                            else None
                        )
                        if payload is not None:
                            route = "runtime-exact-stale"
                            if not degradation:
                                degradation.append(
                                    {
                                        "target": "canonical-record",
                                        "state": "missing",
                                        "fallback": "runtime-stale-with-provenance",
                                    }
                                )
                    except (RuntimeError, sqlite3.Error):
                        payload = None
            else:
                try:
                    with self._exact() as connection:
                        node = exact.read_record(
                            connection, record_id, access_scopes=self.access_scopes
                        )
                        documents = exact.documents_for_node(
                            connection,
                            record_id,
                            access_scopes=self.access_scopes,
                            detail="summary" if detail == "full" else detail,
                            limit=MAX_PAGE_SIZE,
                        )
                        document_count = exact.document_count_for_node(
                            connection,
                            record_id,
                            access_scopes=self.access_scopes,
                        )
                    payload = (
                        {
                            "record": node,
                            "documents": documents,
                            "document_count": document_count,
                        }
                        if node
                        else None
                    )
                except (RuntimeError, sqlite3.Error):
                    payload = None
                if payload is None and self.canonical and owner:
                    try:
                        payload = self.canonical.read_record(
                            owner, record_id, access_scopes=set(self.access_scopes)
                        )
                        route = "canonical-repo-local"
                    except (KeyError, OSError, RuntimeError, ValueError) as exc:
                        degradation.append(
                            {
                                "target": "canonical-owner-source",
                                "state": "unavailable",
                                "fallback": "empty",
                                "reason": type(exc).__name__,
                            }
                        )
        elif resource_class == "documents" and len(parts) == 1:
            with self._exact() as connection:
                payload = exact.read_document(
                    connection,
                    parts[0],
                    access_scopes=self.access_scopes,
                    detail=detail,
                )
        elif resource_class == "sources" and len(parts) == 2:
            owner, document_id = parts
            with self._exact() as connection:
                document = exact.read_document(
                    connection,
                    document_id,
                    access_scopes=self.access_scopes,
                    detail="full",
                )
            payload = document if document and document.get("repo") == owner else None
        elif resource_class == "evidence" and len(parts) == 1:
            payload = self._trace_value(parts[0])
            route = "runtime-trace"
        elif resource_class == "schemas" and len(parts) == 1:
            payload = self.canonical.schema(parts[0]) if self.canonical else None
            route = "aoa-kag-schema"
        elif resource_class == "projections" and len(parts) == 1:
            payload = self._current() if parts[0] == projection["digest"] else None
            route = "runtime-state"
        else:
            raise ValueError("unsupported KAG resource URI")
        if (
            resource_class in {"records", "anchors"}
            and detail == "full"
            and isinstance(payload, dict)
            and isinstance(payload.get("record"), dict)
            and payload["record"].get("record_form") == "projection_handle"
            and not any(
                item.get("target") == "canonical-record" for item in degradation
            )
        ):
            degradation.append(
                {
                    "target": "canonical-record",
                    "state": "unavailable",
                    "fallback": "runtime-projection-handle",
                }
            )
        payload = self._bounded_payload(payload)
        trace_id = self._trace(
            {
                "operation": "read",
                "uri": uri,
                "route": route,
                "degradation": degradation,
                "projection": projection,
                "found": payload is not None,
            }
        )
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "operation": "read",
            "status": (
                "degraded"
                if payload is not None and degradation
                else ("ok" if payload is not None else "empty")
            ),
            "trace_id": trace_id,
            "route": {"adapter": route, "degradation": degradation},
            "projection": projection,
            "resource": {"uri": uri, "detail": detail, "payload": payload},
            "resources": {"evidence": _resource_uri("evidence", trace_id)},
        }

    @classmethod
    def _bounded_payload(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [cls._bounded_payload(item) for item in value]
        if not isinstance(value, dict):
            return value
        payload = {key: cls._bounded_payload(item) for key, item in value.items()}
        text = payload.get("text")
        if isinstance(text, str):
            payload["text"] = text[:MAX_FULL_TEXT_CHARS]
            payload["text_chars"] = len(text)
            payload["text_truncated"] = len(text) > MAX_FULL_TEXT_CHARS
            inspection = _content_inspection({"text": text})
            if inspection:
                payload["content_inspection"] = inspection
        return payload

    def traverse(
        self,
        source_ids: list[str],
        *,
        owner: str | None = None,
        query: str = "",
        direction: str = "outgoing",
        relation_kinds: list[str] | None = None,
        max_depth: int = 2,
        detail: str = "compact",
        limit: int = 10,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not source_ids:
            raise ValueError("source_ids must be non-empty")
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError(f"unsupported traversal direction: {direction}")
        if not 1 <= max_depth <= MAX_TRAVERSAL_DEPTH:
            raise ValueError(f"max_depth must be from 1 through {MAX_TRAVERSAL_DEPTH}")
        if detail not in DETAIL_LEVELS:
            raise ValueError(f"unsupported detail level: {detail}")
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be from 1 through {MAX_PAGE_SIZE}")
        source_ids = list(dict.fromkeys(source_ids))
        request = {
            "source_ids": source_ids,
            "owner": owner,
            "query": query,
            "direction": direction,
            "relation_kinds": sorted(set(relation_kinds or [])),
            "max_depth": max_depth,
            "detail": detail,
            "limit": limit,
        }
        request_digest = _request_digest(request)
        offset = _decode_cursor(cursor, request_digest)
        projection = self._projection()
        degradation: list[dict[str, Any]] = []
        routes: list[dict[str, Any]] = []
        raw_hits: list[dict[str, Any]] = []
        owner_freshness = self._owner_freshness(owner) if owner else {"state": "mixed"}
        if owner and owner_freshness["state"] == "stale":
            degradation.append(
                {
                    "target": "graph-owner-snapshot",
                    "state": "stale",
                    "fallback": "runtime-stale-with-provenance",
                }
            )
        try:
            if projection["targets"]["graph"]["state"] != "current":
                raise RuntimeError("graph projection is unavailable")
            graph_client = JsonHttpClient(
                self.config.neo4j_url,
                headers=_neo4j_headers(self.config.stack_root),
                timeout=self.config.http_timeout,
            )
            graph_projection = graph.Neo4jProjection(
                graph_client, self.config.neo4j_database
            )
            raw_hits, latency = graph.traverse(
                graph=graph_projection,
                projection=projection["digest"],
                source_ids=source_ids,
                direction=direction,
                relation_kinds=relation_kinds,
                owner=owner,
                access_scopes=list(self.access_scopes),
                max_depth=max_depth,
                offset=offset,
                limit=limit + 1,
            )
            routes.append({"adapter": "neo4j-graph", "latency_ms": latency})
        except (RuntimeError, OSError) as exc:
            seed_owners = {self._record_owner(item) for item in source_ids}
            seed_owners.discard(None)
            canonical_owner = owner or (
                next(iter(seed_owners)) if len(seed_owners) == 1 else None
            )
            try:
                with self._exact() as connection:
                    raw_hits, latency = exact.traverse_records(
                        connection,
                        source_ids,
                        direction=direction,
                        relation_kinds=relation_kinds,
                        owner=owner,
                        access_scopes=self.access_scopes,
                        max_depth=max_depth,
                        offset=offset,
                        limit=limit + 1,
                    )
                routes.append(
                    {
                        "adapter": "sqlite-exact-relations",
                        "latency_ms": latency,
                    }
                )
                degradation.append(
                    {
                        "target": "graph",
                        "state": "unavailable",
                        "fallback": "sqlite-exact-relations",
                        "reason": type(exc).__name__,
                    }
                )
            except (RuntimeError, sqlite3.Error, OSError) as exact_exc:
                degradation.append(
                    {
                        "target": "exact-relations",
                        "state": "unavailable",
                        "fallback": (
                            "canonical-repo-local"
                            if self.canonical and canonical_owner
                            else "empty-bounded-result"
                        ),
                        "reason": type(exact_exc).__name__,
                    }
                )
                if self.canonical and canonical_owner:
                    started = time.perf_counter()
                    canonical_succeeded = False
                    try:
                        raw_hits = self.canonical.traverse_owner(
                            canonical_owner,
                            source_ids,
                            query=query,
                            relation_kinds=(
                                set(relation_kinds) if relation_kinds else None
                            ),
                            max_depth=max_depth,
                            access_scopes=set(self.access_scopes),
                            limit=offset + limit + 1,
                        )[offset:]
                        canonical_succeeded = True
                        routes.append(
                            {
                                "adapter": "canonical-repo-local",
                                "latency_ms": (time.perf_counter() - started) * 1000,
                            }
                        )
                    except (
                        KeyError,
                        OSError,
                        RuntimeError,
                        ValueError,
                    ) as canonical_exc:
                        raw_hits = []
                        degradation.append(
                            {
                                "target": f"canonical-owner:{canonical_owner}",
                                "state": "unavailable",
                                "fallback": "empty-bounded-result",
                                "reason": type(canonical_exc).__name__,
                            }
                        )
                degradation.append(
                    {
                        "target": "graph",
                        "state": "unavailable",
                        "fallback": (
                            "canonical-repo-local"
                            if self.canonical
                            and canonical_owner
                            and canonical_succeeded
                            else "empty-bounded-result"
                        ),
                        "reason": type(exc).__name__,
                    }
                )
        has_more = len(raw_hits) > limit
        raw_hits = raw_hits[:limit]
        if raw_hits:
            try:
                enrichment_started = time.perf_counter()
                with self._exact() as connection:
                    for hit in raw_hits:
                        record = exact.read_record(
                            connection,
                            str(hit.get("id") or ""),
                            access_scopes=self.access_scopes,
                        )
                        if record:
                            for key, value in record.items():
                                if hit.get(key) in (None, "", [], {}):
                                    hit[key] = value
                            if detail == "full":
                                hit["record"] = record
                        documents = exact.documents_for_node(
                            connection,
                            str(hit.get("id") or ""),
                            access_scopes=self.access_scopes,
                            detail=detail,
                            limit=1,
                        )
                        if not documents:
                            record_sources = hit.get("source_record_ids")
                            source_id = (
                                str(record_sources[0])
                                if isinstance(record_sources, list) and record_sources
                                else ""
                            )
                            if source_id:
                                documents = exact.documents_for_node(
                                    connection,
                                    source_id,
                                    access_scopes=self.access_scopes,
                                    detail=detail,
                                    limit=1,
                                )
                        if not documents:
                            continue
                        document = documents[0]
                        for key in (
                            "label",
                            "path",
                            "locator",
                            "abi",
                            "signs",
                            "profiles",
                            "provenance",
                            "provenance_ref",
                            "temporal_ref",
                            "trust_ref",
                            "document_id",
                            "document_role",
                            "surface_state",
                            "snippet",
                            "text",
                        ):
                            if document.get(key) is None:
                                continue
                            if key in {"document_id", "locator", "snippet", "text"}:
                                hit[key] = document[key]
                            elif hit.get(key) in (None, "", [], {}):
                                hit[key] = document[key]
                routes.append(
                    {
                        "adapter": "sqlite-graph-enrichment",
                        "latency_ms": (time.perf_counter() - enrichment_started) * 1000,
                    }
                )
            except (RuntimeError, sqlite3.Error):
                degradation.append(
                    {
                        "target": "graph-node-enrichment",
                        "state": "unavailable",
                        "fallback": "graph-path-metadata",
                    }
                )
        normalized: list[dict[str, Any]] = []
        for hit in raw_hits:
            if "qualified_id" in hit:
                normalized.append(hit)
                continue
            repo = str(
                hit.get("repo")
                or self._record_owner(str(hit.get("id") or ""))
                or owner
                or ""
            )
            normalized.append(
                self._normalize_hit(
                    hit,
                    strategy="graph",
                    projection=projection,
                    freshness=self._owner_freshness(repo)
                    if repo
                    else {"state": "unknown"},
                    detail=detail,
                )
            )
        trace_payload = {
            "operation": "traverse",
            "request": request,
            "route": {"adapters": routes, "degradation": degradation},
            "projection": projection,
            "evidence_paths": [
                item.get("evidence_path")
                for item in normalized
                if item.get("evidence_path")
            ],
        }
        trace_id = self._trace(trace_payload)
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "operation": "traverse",
            "status": "degraded"
            if degradation
            else ("empty" if not normalized else "ok"),
            "trace_id": trace_id,
            "query": request,
            "route": trace_payload["route"],
            "projection": projection,
            "page": {
                "limit": limit,
                "offset": offset,
                "count": len(normalized),
                "next_cursor": (
                    _encode_cursor(offset + len(normalized), request_digest)
                    if has_more
                    else None
                ),
            },
            "results": normalized,
            "resources": {"evidence": _resource_uri("evidence", trace_id)},
        }

    def explain(
        self,
        trace_id: str,
        *,
        detail: str = "summary",
    ) -> dict[str, Any]:
        if detail not in DETAIL_LEVELS:
            raise ValueError(f"unsupported detail level: {detail}")
        trace = self._trace_value(trace_id)
        if trace is not None and detail == "compact":
            trace = {
                "operation": trace.get("operation"),
                "route": trace.get("route"),
                "projection": trace.get("projection"),
                "result_ids": trace.get("result_ids", []),
            }
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "operation": "explain",
            "status": "ok" if trace is not None else "empty",
            "trace_id": trace_id,
            "detail": detail,
            "explanation": trace,
            "resources": {"evidence": _resource_uri("evidence", trace_id)},
        }
