from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .bundle import RetrievalBundle, canonical_json, sha256_file


SCHEMA_VERSION = "abyss-stack-repo-self-kag-sqlite-v2"


def _batches(
    rows: Iterable[Sequence[Any]], size: int = 1000
) -> Iterator[list[Sequence[Any]]]:
    batch: list[Sequence[Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _insert_many(
    connection: sqlite3.Connection,
    statement: str,
    rows: Iterable[Sequence[Any]],
) -> int:
    count = 0
    for batch in _batches(rows):
        connection.executemany(statement, batch)
        count += len(batch)
    return count


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = MEMORY;
        PRAGMA user_version = 1;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE owners (
            repo TEXT PRIMARY KEY,
            namespace TEXT NOT NULL,
            payload_json TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            repo TEXT NOT NULL,
            namespace TEXT NOT NULL,
            node_class TEXT NOT NULL,
            kind TEXT NOT NULL,
            access_scope TEXT NOT NULL,
            payload_json TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE INDEX nodes_repo_class ON nodes(repo, node_class);
        CREATE INDEX nodes_kind ON nodes(kind);

        CREATE TABLE relations (
            id TEXT PRIMARY KEY,
            relation_kind TEXT NOT NULL,
            from_id TEXT NOT NULL,
            to_id TEXT NOT NULL,
            source_repo TEXT NOT NULL,
            target_repo TEXT NOT NULL,
            scope TEXT NOT NULL,
            evidence_class TEXT NOT NULL,
            confidence REAL NOT NULL,
            payload_json TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE INDEX relations_from ON relations(from_id, relation_kind);
        CREATE INDEX relations_to ON relations(to_id, relation_kind);
        CREATE INDEX relations_repos ON relations(source_repo, target_repo);

        CREATE TABLE external_references (
            id TEXT PRIMARY KEY,
            source_repo TEXT NOT NULL,
            source_anchor_id TEXT NOT NULL,
            target_repo TEXT,
            target_ref TEXT NOT NULL,
            reference_kind TEXT NOT NULL,
            payload_json TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE INDEX external_refs_source ON external_references(source_repo, source_anchor_id);

        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            vector_point_id TEXT NOT NULL UNIQUE,
            repo TEXT NOT NULL,
            namespace TEXT NOT NULL,
            node_id TEXT NOT NULL,
            node_class TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            text_digest TEXT NOT NULL,
            access_scope TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE INDEX documents_repo_path ON documents(repo, path, start_line);
        CREATE INDEX documents_node ON documents(node_id);
        CREATE INDEX documents_kind ON documents(node_class, kind);
        CREATE INDEX documents_filter ON documents(
            repo, path, node_class, kind, start_line, chunk_index, id
        );
        CREATE INDEX documents_digest ON documents(text_digest);

        CREATE VIRTUAL TABLE documents_fts USING fts5(
            id UNINDEXED,
            repo,
            node_class,
            kind,
            path,
            label,
            text,
            tokenize = 'unicode61'
        );
        """
    )


def _owner_rows(bundle: RetrievalBundle) -> Iterator[Sequence[Any]]:
    for record in bundle.records("owners"):
        repo = record["repo"]
        yield (str(repo["name"]), str(repo["namespace"]), canonical_json(record))


def _node_rows(bundle: RetrievalBundle) -> Iterator[Sequence[Any]]:
    for record in bundle.records("nodes"):
        yield (
            str(record["id"]),
            str(record["repo"]),
            str(record["namespace"]),
            str(record["node_class"]),
            str(record["kind"]),
            str(record["access_scope"]),
            canonical_json(record),
        )


def _relation_rows(bundle: RetrievalBundle) -> Iterator[Sequence[Any]]:
    for record in bundle.records("relations"):
        yield (
            str(record["id"]),
            str(record["relation_kind"]),
            str(record["from_id"]),
            str(record["to_id"]),
            str(record["source_repo"]),
            str(record["target_repo"]),
            str(record["scope"]),
            str(record["evidence_class"]),
            float(record["confidence"]),
            canonical_json(record),
        )


def _external_rows(bundle: RetrievalBundle) -> Iterator[Sequence[Any]]:
    for record in bundle.records("external_references"):
        identifier = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
        yield (
            identifier,
            str(record["source_repo"]),
            str(record["source_anchor_id"]),
            record.get("target_repo"),
            str(record["target_ref"]),
            str(record["reference_kind"]),
            canonical_json(record),
        )


def _document_rows(
    bundle: RetrievalBundle,
) -> Iterator[tuple[Sequence[Any], Sequence[Any]]]:
    for record in bundle.records("documents"):
        locator = record["locator"]
        metadata = {key: value for key, value in record.items() if key != "text"}
        row = (
            str(record["id"]),
            str(record["version_id"]),
            str(record["vector_point_id"]),
            str(record["repo"]),
            str(record["namespace"]),
            str(record["node_id"]),
            str(record["node_class"]),
            str(record["kind"]),
            str(record["label"]),
            str(record["path"]),
            int(locator["start_line"]),
            int(locator["end_line"]),
            int(record["chunk_index"]),
            str(record["text"]),
            str(record["text_digest"]),
            str(record["access"]["scope"]),
            canonical_json(metadata),
        )
        fts_row = (
            str(record["id"]),
            str(record["repo"]),
            str(record["node_class"]),
            str(record["kind"]),
            str(record["path"]),
            str(record["label"]),
            str(record["text"]),
        )
        yield row, fts_row


def materialize(bundle: RetrievalBundle, destination: Path) -> dict[str, Any]:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        _create_schema(connection)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "bundle_digest": bundle.bundle_digest,
            "projection_digest": bundle.projection_digest,
            "federation_digest": bundle.federation_digest,
            "embedding_profile": canonical_json(bundle.manifest["embedding_profile"]),
        }
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            sorted(metadata.items()),
        )
        counts = {
            "owners": _insert_many(
                connection,
                "INSERT INTO owners(repo, namespace, payload_json) VALUES (?, ?, ?)",
                _owner_rows(bundle),
            ),
            "nodes": _insert_many(
                connection,
                "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?)",
                _node_rows(bundle),
            ),
            "relations": _insert_many(
                connection,
                "INSERT INTO relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _relation_rows(bundle),
            ),
            "external_references": _insert_many(
                connection,
                "INSERT INTO external_references VALUES (?, ?, ?, ?, ?, ?, ?)",
                _external_rows(bundle),
            ),
        }
        document_count = 0
        for batch in _batches(_document_rows(bundle)):
            connection.executemany(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [row for row, _ in batch],
            )
            connection.executemany(
                "INSERT INTO documents_fts(id, repo, node_class, kind, path, label, text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [fts_row for _, fts_row in batch],
            )
            document_count += len(batch)
        counts["documents"] = document_count
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    connection.close()

    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
    digest, size = sha256_file(destination)
    return {
        "schema_version": SCHEMA_VERSION,
        "path": str(destination),
        "sha256": digest,
        "bytes": size,
        "counts": counts,
    }


def check(bundle: RetrievalBundle, destination: Path) -> dict[str, Any]:
    destination = destination.resolve()
    if not destination.is_file():
        raise RuntimeError(f"missing SQLite projection: {destination}")
    connection = sqlite3.connect(f"file:{destination}?mode=ro&immutable=1", uri=True)
    try:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError("SQLite projection schema mismatch")
        if metadata.get("bundle_digest") != bundle.bundle_digest:
            raise RuntimeError("SQLite projection bundle mismatch")
        if metadata.get("projection_digest") != bundle.projection_digest:
            raise RuntimeError("SQLite projection identity mismatch")
        counts = {
            key: int(connection.execute(f"SELECT count(*) FROM {key}").fetchone()[0])
            for key in (
                "owners",
                "nodes",
                "relations",
                "external_references",
                "documents",
                "documents_fts",
            )
        }
        if counts["documents"] != counts.pop("documents_fts"):
            raise RuntimeError("SQLite FTS document count mismatch")
        expected = {
            key: int(bundle.manifest["files"][key]["record_count"]) for key in counts
        }
        if counts != expected:
            raise RuntimeError(
                f"SQLite projection counts mismatch: {counts} != {expected}"
            )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    finally:
        connection.close()
    digest, size = sha256_file(destination)
    return {
        "schema_version": SCHEMA_VERSION,
        "path": str(destination),
        "sha256": digest,
        "bytes": size,
        "counts": counts,
    }


def _document_hit(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "payload": json.loads(row["metadata_json"])}


def _fts_expression(value: str, operator: str) -> str:
    tokens = re.findall(r"\w+", value.casefold(), flags=re.UNICODE)
    return f" {operator} ".join(
        f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens
    )


def _fts_literal(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def search_exact(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    rows = connection.execute(
        "SELECT * FROM documents WHERE id=? LIMIT ?",
        (query, limit),
    ).fetchall()
    if not rows:
        rows = connection.execute(
            "SELECT * FROM documents WHERE path=? "
            "ORDER BY repo,start_line,chunk_index,id LIMIT ?",
            (query, limit),
        ).fetchall()
    if not rows:
        rows = connection.execute(
            "SELECT * FROM documents WHERE label=? "
            "ORDER BY repo,path,start_line,id LIMIT ?",
            (query, limit),
        ).fetchall()
    return [_document_hit(row) for row in rows], (time.perf_counter() - started) * 1000


def search_filter(
    connection: sqlite3.Connection,
    *,
    repo: str,
    path: str,
    node_class: str,
    kind: str,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    rows = connection.execute(
        "SELECT * FROM documents WHERE repo=? AND path=? AND node_class=? AND kind=? "
        "ORDER BY start_line, chunk_index, id LIMIT ?",
        (repo, path, node_class, kind, limit),
    ).fetchall()
    return [_document_hit(row) for row in rows], (time.perf_counter() - started) * 1000


def search_lexical(
    connection: sqlite3.Connection,
    query: str,
    *,
    repo: str | None = None,
    kind: str | None = None,
    operator: str = "AND",
    limit: int = 10,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    expression = _fts_expression(query, operator)
    if not expression:
        return [], 0.0
    fts_columns = [
        str(row[1]) for row in connection.execute("PRAGMA table_info(documents_fts)")
    ]
    schema_version = connection.execute(
        "SELECT value FROM metadata WHERE key='schema_version'"
    ).fetchone()[0]
    scoped_columns = set(fts_columns) if str(schema_version).endswith("-v2") else set()
    clauses: list[str] = []
    values: list[Any] = [expression]
    scopes: list[str] = []
    if repo and "repo" in scoped_columns:
        scopes.append(f"repo:{_fts_literal(repo)}")
    elif repo:
        clauses.append("d.repo=?")
        values.append(repo)
    if kind and "kind" in scoped_columns:
        scopes.append(f"kind:{_fts_literal(kind)}")
    elif kind:
        clauses.append("d.kind=?")
        values.append(kind)
    if scopes:
        values[0] = " AND ".join((*scopes, f"({expression})"))
    filter_clause = " AND " + " AND ".join(clauses) if clauses else ""
    weights_by_column = {
        "id": 0.0,
        "repo": 0.0,
        "node_class": 0.0,
        "kind": 0.0,
        "path": 2.0,
        "label": 10.0,
        "text": 1.0,
    }
    weights = ", ".join(
        str(weights_by_column.get(column, 1.0)) for column in fts_columns
    )
    values.append(limit)
    rows = connection.execute(
        "SELECT d.* FROM documents_fts f JOIN documents d ON d.id=f.id "
        f"WHERE documents_fts MATCH ?{filter_clause} "
        f"ORDER BY bm25(documents_fts, {weights}), d.id LIMIT ?",
        tuple(values),
    ).fetchall()
    return [_document_hit(row) for row in rows], (time.perf_counter() - started) * 1000
