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


SCHEMA_VERSION = "abyss-stack-repo-self-kag-sqlite-v4"


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

        CREATE TABLE records (
            id TEXT PRIMARY KEY,
            repo TEXT NOT NULL,
            namespace TEXT NOT NULL,
            node_class TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            path TEXT NOT NULL,
            search_text TEXT NOT NULL,
            document_role TEXT NOT NULL,
            surface_state TEXT NOT NULL,
            access_scope TEXT NOT NULL,
            provenance_ref TEXT NOT NULL,
            temporal_ref TEXT NOT NULL,
            trust_ref TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX records_repo_class ON records(repo, node_class, kind, id);
        CREATE INDEX records_path ON records(path, repo, node_class, kind, id);
        CREATE INDEX records_label ON records(label, repo, node_class, kind, id);
        CREATE INDEX records_role ON records(document_role, surface_state, id);

        CREATE VIEW nodes AS
        SELECT id,repo,namespace,node_class,kind,access_scope,payload_json
        FROM records WHERE node_class!='relation';

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
            evidence_anchor_count INTEGER NOT NULL,
            provenance_ref TEXT NOT NULL,
            temporal_ref TEXT NOT NULL,
            trust_ref TEXT NOT NULL
        );
        CREATE INDEX relations_from ON relations(from_id, relation_kind);
        CREATE INDEX relations_to ON relations(to_id, relation_kind);
        CREATE INDEX relations_repos ON relations(source_repo, target_repo);

        CREATE VIRTUAL TABLE records_fts USING fts5(
            repo,
            node_class,
            kind,
            path,
            label,
            document_role,
            surface_state,
            search_text,
            content = 'records',
            content_rowid = 'rowid',
            detail = column,
            tokenize = 'unicode61'
        );

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
            document_role TEXT NOT NULL,
            surface_state TEXT NOT NULL,
            access_scope TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );
        CREATE INDEX documents_path ON documents(
            path, repo, node_class, kind, start_line, chunk_index, id
        );
        CREATE INDEX documents_label ON documents(
            label, repo, node_class, kind, start_line, chunk_index, id
        );
        CREATE INDEX documents_node ON documents(node_id);
        CREATE INDEX documents_repo_class ON documents(
            repo, node_class, kind, path, start_line, chunk_index, id
        );
        CREATE INDEX documents_role ON documents(document_role, surface_state, id);
        CREATE INDEX documents_digest ON documents(text_digest);

        CREATE VIRTUAL TABLE documents_fts USING fts5(
            repo,
            node_class,
            kind,
            path,
            label,
            document_role,
            surface_state,
            text,
            content = 'documents',
            content_rowid = 'rowid',
            detail = column,
            tokenize = 'unicode61'
        );
        """
    )


def _owner_rows(bundle: RetrievalBundle) -> Iterator[Sequence[Any]]:
    for record in bundle.records("owners"):
        repo = record["repo"]
        yield (str(repo["name"]), str(repo["namespace"]), canonical_json(record))


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
            len(record["evidence_anchor_ids"]),
            str(record["provenance_ref"]),
            str(record["temporal_ref"]),
            str(record["trust_ref"]),
        )


def _record_rows(
    bundle: RetrievalBundle,
) -> Iterator[Sequence[Any]]:
    for key in ("nodes", "relations"):
        for record in bundle.records(key):
            relation = key == "relations"
            repo = str(record["source_repo"] if relation else record["repo"])
            namespace = str(record.get("namespace") or f"aoa:{repo}")
            node_class = "relation" if relation else str(record["node_class"])
            kind = str(record["relation_kind"] if relation else record["kind"])
            row = (
                str(record["id"]),
                repo,
                namespace,
                node_class,
                kind,
                str(record["label"]),
                str(record["path"]),
                str(record["search_text"]),
                str(record["document_role"]),
                str(record["surface_state"]),
                str(record["access_scope"]),
                str(record["provenance_ref"]),
                str(record["temporal_ref"]),
                str(record["trust_ref"]),
                canonical_json(record),
            )
            yield row


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
) -> Iterator[Sequence[Any]]:
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
            str(record["document_role"]),
            str(record["surface_state"]),
            str(record["access"]["scope"]),
            canonical_json(metadata),
        )
        yield row


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
        }
        counts["records"] = _insert_many(
            connection,
            "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _record_rows(bundle),
        )
        counts["nodes"] = int(bundle.manifest["files"]["nodes"]["record_count"])
        counts["relations"] = _insert_many(
            connection,
            "INSERT INTO relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _relation_rows(bundle),
        )
        if counts["records"] != counts["nodes"] + counts["relations"]:
            raise RuntimeError(
                "record projection count does not match nodes plus relations"
            )
        counts["external_references"] = _insert_many(
            connection,
            "INSERT INTO external_references VALUES (?, ?, ?, ?, ?, ?, ?)",
            _external_rows(bundle),
        )
        counts["documents"] = _insert_many(
            connection,
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _document_rows(bundle),
        )
        connection.execute("INSERT INTO records_fts(records_fts) VALUES ('rebuild')")
        connection.execute(
            "INSERT INTO documents_fts(documents_fts) VALUES ('rebuild')"
        )
        connection.execute(
            "INSERT INTO records_fts(records_fts, rank) VALUES ('integrity-check', 1)"
        )
        connection.execute(
            "INSERT INTO documents_fts(documents_fts, rank) VALUES ('integrity-check', 1)"
        )
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
                "records",
                "records_fts",
                "external_references",
                "documents",
                "documents_fts",
            )
        }
        if counts["documents"] != counts.pop("documents_fts"):
            raise RuntimeError("SQLite FTS document count mismatch")
        if counts["records"] != counts.pop("records_fts"):
            raise RuntimeError("SQLite FTS record count mismatch")
        expected = {
            key: int(bundle.manifest["files"][key]["record_count"])
            for key in counts
            if key != "records"
        }
        expected["records"] = expected["nodes"] + expected["relations"]
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


def _fts_tokens(value: str) -> list[str]:
    return re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE)


def _fts_expression(value: str, operator: str) -> str:
    tokens = _fts_tokens(value)
    return f" {operator} ".join(
        f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens
    )


def _fts_literal(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _exact_union_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    query: str,
    query_fields: Sequence[str],
    clauses: Sequence[str],
    clause_values: Sequence[Any],
    order_by: str,
    limit: int,
    offset: int,
) -> list[sqlite3.Row]:
    branches: list[str] = []
    values: list[Any] = []
    for priority, field in enumerate(query_fields):
        branch_clauses = [f"{field}=?"]
        branch_values: list[Any] = [query]
        for previous in query_fields[:priority]:
            branch_clauses.append(f"{previous}!=?")
            branch_values.append(query)
        branch_clauses.extend(clauses)
        branch_values.extend(clause_values)
        branches.append(
            f"SELECT source.*,{priority} AS match_priority FROM {table} source "
            f"WHERE {' AND '.join(branch_clauses)}"
        )
        values.extend(branch_values)
    values.extend((limit, offset))
    return connection.execute(
        "SELECT * FROM (" + " UNION ALL ".join(branches) + ") "
        f"ORDER BY match_priority,{order_by} LIMIT ? OFFSET ?",
        tuple(values),
    ).fetchall()


def _scoped_fts_expression(
    expression: str,
    columns: set[str],
    scopes: Sequence[tuple[str, str | None]],
) -> str:
    terms: list[str] = []
    for column, value in scopes:
        if not value or column not in columns:
            continue
        tokens = _fts_tokens(value)
        if not tokens:
            continue
        scoped = " AND ".join(f"{column}:{_fts_literal(token)}" for token in tokens)
        terms.append(f"({scoped})")
    if not terms:
        return expression
    return " AND ".join((*terms, f"({expression})"))


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
    scoped_columns = (
        set(fts_columns)
        if str(schema_version).endswith(("-v2", "-v3"))
        or str(schema_version).endswith("-v4")
        else set()
    )
    clauses: list[str] = []
    values: list[Any] = []
    if repo:
        clauses.append("d.repo=?")
        values.append(repo)
    if kind:
        clauses.append("d.kind=?")
        values.append(kind)
    match_expression = _scoped_fts_expression(
        expression,
        scoped_columns,
        (("repo", repo), ("kind", kind)),
    )
    filter_clause = " AND " + " AND ".join(clauses) if clauses else ""
    weights_by_column = {
        "id": 0.0,
        "repo": 0.0,
        "node_class": 0.0,
        "kind": 0.0,
        "path": 2.0,
        "label": 10.0,
        "document_role": 0.0,
        "surface_state": 0.0,
        "text": 1.0,
    }
    weights = ", ".join(
        str(weights_by_column.get(column, 1.0)) for column in fts_columns
    )
    if "id" in fts_columns:
        statement = (
            "SELECT d.* FROM documents_fts f JOIN documents d ON d.id=f.id "
            f"WHERE documents_fts MATCH ?{filter_clause} "
            f"ORDER BY bm25(documents_fts,{weights}),d.id LIMIT ?"
        )
        parameters = (match_expression, *values, limit)
    else:
        statement = (
            "SELECT d.* FROM documents_fts "
            "CROSS JOIN documents d ON d.rowid=documents_fts.rowid "
            "WHERE documents_fts MATCH ? AND documents_fts.rank MATCH ?"
            f"{filter_clause} ORDER BY documents_fts.rank,d.id LIMIT ?"
        )
        parameters = (match_expression, f"bm25({weights})", *values, limit)
    rows = connection.execute(statement, parameters).fetchall()
    return [_document_hit(row) for row in rows], (time.perf_counter() - started) * 1000


def document_payload(
    row: sqlite3.Row,
    *,
    detail: str = "compact",
    snippet_chars: int = 480,
) -> dict[str, Any]:
    """Return one retrieval document without exposing SQLite row shape."""
    metadata = json.loads(row["metadata_json"])
    payload = {
        **metadata,
        "document_id": str(row["id"]),
        "id": str(row["node_id"]),
        "repo": str(row["repo"]),
        "namespace": str(row["namespace"]),
        "node_class": str(row["node_class"]),
        "kind": str(row["kind"]),
        "label": str(row["label"]),
        "path": str(row["path"]),
        "locator": {
            **dict(metadata.get("locator") or {}),
            "start_line": int(row["start_line"]),
            "end_line": int(row["end_line"]),
        },
        "access": {
            **dict(metadata.get("access") or {}),
            "scope": str(row["access_scope"]),
        },
        "text_digest": str(row["text_digest"]),
        "document_role": str(metadata.get("document_role") or "none"),
        "surface_state": str(metadata.get("surface_state") or "authored_source"),
    }
    text = str(row["text"])
    if detail == "full":
        payload["text"] = text
    elif detail == "summary":
        payload["snippet"] = text[:snippet_chars]
    return payload


def projection_metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row["key"]): str(row["value"])
        for row in connection.execute("SELECT key,value FROM metadata ORDER BY key")
    }


def owner_records(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        json.loads(row["payload_json"])
        for row in connection.execute("SELECT payload_json FROM owners ORDER BY repo")
    ]


def record_kinds(
    connection: sqlite3.Connection,
    *,
    repo: str | None = None,
    access_scopes: Sequence[str] = ("public",),
) -> list[tuple[str, str, str]]:
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return []
    placeholders = ",".join("?" for _ in scopes)
    if _table_exists(connection, "records"):
        clauses = [f"access_scope IN ({placeholders})"]
        parameters: list[str] = list(scopes)
        if repo:
            clauses.append("repo=?")
            parameters.append(repo)
        rows = connection.execute(
            "SELECT repo,node_class,kind FROM records WHERE "
            + " AND ".join(clauses)
            + " GROUP BY repo,node_class,kind ORDER BY repo,node_class,kind",
            parameters,
        )
        return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]
    node_clauses = [f"access_scope IN ({placeholders})"]
    node_parameters: list[str] = list(scopes)
    if repo:
        node_clauses.append("repo=?")
        node_parameters.append(repo)
    node_rows = connection.execute(
        "SELECT repo,node_class,kind FROM nodes WHERE "
        + " AND ".join(node_clauses)
        + " GROUP BY repo,node_class,kind ORDER BY repo,node_class,kind",
        node_parameters,
    )
    relation_clauses = [
        f"source.access_scope IN ({placeholders})",
        f"target.access_scope IN ({placeholders})",
    ]
    relation_parameters: list[str] = [*scopes, *scopes]
    if repo:
        relation_clauses.append("r.source_repo=?")
        relation_parameters.append(repo)
    relation_rows = connection.execute(
        "SELECT r.source_repo,'relation',r.relation_kind FROM relations r "
        "JOIN nodes source ON source.id=r.from_id "
        "JOIN nodes target ON target.id=r.to_id WHERE "
        + " AND ".join(relation_clauses)
        + " GROUP BY r.source_repo,r.relation_kind "
        "ORDER BY r.source_repo,r.relation_kind",
        relation_parameters,
    )
    values = [(str(row[0]), str(row[1]), str(row[2])) for row in node_rows]
    values.extend((str(row[0]), str(row[1]), str(row[2])) for row in relation_rows)
    return sorted(values)


def read_owner(
    connection: sqlite3.Connection,
    repo: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT payload_json FROM owners WHERE repo=?",
        (repo,),
    ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def read_node(
    connection: sqlite3.Connection,
    record_id: str,
    *,
    access_scopes: Sequence[str] = ("public",),
) -> dict[str, Any] | None:
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return None
    placeholders = ",".join("?" for _ in scopes)
    if _table_exists(connection, "records"):
        row = connection.execute(
            f"SELECT payload_json FROM records WHERE id=? AND node_class!='relation' "
            f"AND access_scope IN ({placeholders})",
            (record_id, *scopes),
        ).fetchone()
    else:
        row = connection.execute(
            f"SELECT payload_json FROM nodes WHERE id=? "
            f"AND access_scope IN ({placeholders})",
            (record_id, *scopes),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def read_relation(
    connection: sqlite3.Connection,
    record_id: str,
    *,
    access_scopes: Sequence[str] = ("public",),
) -> dict[str, Any] | None:
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return None
    placeholders = ",".join("?" for _ in scopes)
    if _table_exists(connection, "records"):
        row = connection.execute(
            f"SELECT payload_json FROM records WHERE id=? AND node_class='relation' "
            f"AND access_scope IN ({placeholders})",
            (record_id, *scopes),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT r.payload_json FROM relations r "
            "JOIN nodes source ON source.id=r.from_id "
            "JOIN nodes target ON target.id=r.to_id "
            f"WHERE r.id=? AND source.access_scope IN ({placeholders}) "
            f"AND target.access_scope IN ({placeholders})",
            (record_id, *scopes, *scopes),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def read_record(
    connection: sqlite3.Connection,
    record_id: str,
    *,
    access_scopes: Sequence[str] = ("public",),
) -> dict[str, Any] | None:
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return None
    if not _table_exists(connection, "records"):
        return read_node(
            connection,
            record_id,
            access_scopes=scopes,
        ) or read_relation(connection, record_id, access_scopes=scopes)
    placeholders = ",".join("?" for _ in scopes)
    row = connection.execute(
        f"SELECT payload_json FROM records WHERE id=? "
        f"AND access_scope IN ({placeholders})",
        (record_id, *scopes),
    ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def record_payload(
    row: sqlite3.Row,
    *,
    detail: str = "compact",
    snippet_chars: int = 480,
) -> dict[str, Any]:
    record = json.loads(row["payload_json"])
    payload = {
        **record,
        "id": str(row["id"]),
        "repo": str(row["repo"]),
        "namespace": str(row["namespace"]),
        "node_class": str(row["node_class"]),
        "kind": str(row["kind"]),
        "label": str(row["label"]),
        "path": str(row["path"]),
        "document_role": str(row["document_role"]),
        "surface_state": str(row["surface_state"]),
        "access_scope": str(row["access_scope"]),
        "provenance_ref": str(row["provenance_ref"]),
        "temporal_ref": str(row["temporal_ref"]),
        "trust_ref": str(row["trust_ref"]),
    }
    search_text = str(row["search_text"])
    payload.pop("search_text", None)
    if detail == "summary":
        payload["snippet"] = search_text[:snippet_chars]
    elif detail == "full":
        payload["record"] = record
    return payload


def search_records_exact(
    connection: sqlite3.Connection,
    query: str,
    *,
    repo: str | None = None,
    node_class: str | None = None,
    kind: str | None = None,
    path: str | None = None,
    path_prefix: str | None = None,
    document_role: str | None = None,
    surface_state: str | None = None,
    access_scopes: Sequence[str] = ("public",),
    detail: str = "compact",
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes or not _table_exists(connection, "records"):
        return [], (time.perf_counter() - started) * 1000
    clauses = [f"access_scope IN ({','.join('?' for _ in scopes)})"]
    values: list[Any] = list(scopes)
    if repo:
        clauses.append("repo=?")
        values.append(repo)
    if node_class:
        clauses.append("node_class=?")
        values.append(node_class)
    if kind:
        clauses.append("kind=?")
        values.append(kind)
    if path:
        clauses.append("path=?")
        values.append(path)
    if path_prefix:
        clauses.append("path LIKE ? ESCAPE '\\'")
        escaped = (
            path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        values.append(f"{escaped}%")
    if document_role:
        clauses.append("document_role=?")
        values.append(document_role)
    else:
        clauses.append("document_role!='evaluation_fixture'")
    if surface_state:
        clauses.append("surface_state=?")
        values.append(surface_state)
    rows = _exact_union_rows(
        connection,
        table="records",
        query=query,
        query_fields=("id", "path", "label"),
        clauses=clauses,
        clause_values=values,
        order_by="repo,node_class,kind,id",
        limit=limit,
        offset=offset,
    )
    return (
        [record_payload(row, detail=detail) for row in rows],
        (time.perf_counter() - started) * 1000,
    )


def search_records_lexical(
    connection: sqlite3.Connection,
    query: str,
    *,
    repo: str | None = None,
    node_class: str | None = None,
    kind: str | None = None,
    path: str | None = None,
    path_prefix: str | None = None,
    document_role: str | None = None,
    surface_state: str | None = None,
    access_scopes: Sequence[str] = ("public",),
    operator: str = "OR",
    detail: str = "compact",
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    expression = _fts_expression(query, operator)
    scopes = tuple(dict.fromkeys(access_scopes))
    if (
        not expression
        or not scopes
        or not _table_exists(connection, "records")
        or not _table_exists(connection, "records_fts")
    ):
        return [], (time.perf_counter() - started) * 1000
    fts_columns = [
        str(row[1]) for row in connection.execute("PRAGMA table_info(records_fts)")
    ]
    match_expression = _scoped_fts_expression(
        expression,
        set(fts_columns),
        (
            ("repo", repo),
            ("node_class", node_class),
            ("kind", kind),
            ("document_role", document_role),
            ("surface_state", surface_state),
        ),
    )
    clauses = [f"r.access_scope IN ({','.join('?' for _ in scopes)})"]
    values: list[Any] = list(scopes)
    if repo:
        clauses.append("r.repo=?")
        values.append(repo)
    if node_class:
        clauses.append("r.node_class=?")
        values.append(node_class)
    if kind:
        clauses.append("r.kind=?")
        values.append(kind)
    if path:
        clauses.append("r.path=?")
        values.append(path)
    if path_prefix:
        clauses.append("r.path LIKE ? ESCAPE '\\'")
        escaped = (
            path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        values.append(f"{escaped}%")
    if document_role:
        clauses.append("r.document_role=?")
        values.append(document_role)
    else:
        clauses.append("r.document_role!='evaluation_fixture'")
    if surface_state:
        clauses.append("r.surface_state=?")
        values.append(surface_state)
    weights_by_column = {
        "id": 0.0,
        "repo": 0.0,
        "node_class": 0.0,
        "kind": 0.0,
        "path": 2.0,
        "label": 10.0,
        "document_role": 0.0,
        "surface_state": 0.0,
        "text": 1.0,
        "search_text": 1.0,
    }
    weights = ",".join(
        str(weights_by_column.get(column, 1.0)) for column in fts_columns
    )
    if "id" in fts_columns:
        statement = (
            "SELECT r.*,bm25(records_fts," + weights + ") AS lexical_rank "
            "FROM records_fts f JOIN records r ON r.id=f.id "
            f"WHERE records_fts MATCH ? AND {' AND '.join(clauses)} "
            "ORDER BY lexical_rank,r.id LIMIT ? OFFSET ?"
        )
        parameters = (match_expression, *values, limit, offset)
    else:
        statement = (
            "SELECT r.*,records_fts.rank AS lexical_rank "
            "FROM records_fts CROSS JOIN records r "
            "ON r.rowid=records_fts.rowid "
            "WHERE records_fts MATCH ? AND records_fts.rank MATCH ? AND "
            f"{' AND '.join(clauses)} "
            "ORDER BY records_fts.rank,r.id LIMIT ? OFFSET ?"
        )
        parameters = (
            match_expression,
            f"bm25({weights})",
            *values,
            limit,
            offset,
        )
    rows = connection.execute(statement, parameters).fetchall()
    hits: list[dict[str, Any]] = []
    for row in rows:
        payload = record_payload(row, detail=detail)
        payload["lexical_rank"] = float(row["lexical_rank"])
        hits.append(payload)
    return hits, (time.perf_counter() - started) * 1000


def read_document(
    connection: sqlite3.Connection,
    document_id: str,
    *,
    access_scopes: Sequence[str] = ("public",),
    detail: str = "full",
) -> dict[str, Any] | None:
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return None
    placeholders = ",".join("?" for _ in scopes)
    row = connection.execute(
        f"SELECT * FROM documents WHERE id=? AND access_scope IN ({placeholders})",
        (document_id, *scopes),
    ).fetchone()
    return document_payload(row, detail=detail) if row else None


def documents_for_node(
    connection: sqlite3.Connection,
    record_id: str,
    *,
    access_scopes: Sequence[str] = ("public",),
    detail: str = "summary",
    limit: int = 20,
) -> list[dict[str, Any]]:
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return []
    placeholders = ",".join("?" for _ in scopes)
    rows = connection.execute(
        f"SELECT * FROM documents WHERE node_id=? AND access_scope IN ({placeholders}) "
        "ORDER BY start_line,chunk_index,id LIMIT ?",
        (record_id, *scopes, limit),
    ).fetchall()
    return [document_payload(row, detail=detail) for row in rows]


def document_count_for_node(
    connection: sqlite3.Connection,
    record_id: str,
    *,
    access_scopes: Sequence[str] = ("public",),
) -> int:
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return 0
    placeholders = ",".join("?" for _ in scopes)
    row = connection.execute(
        f"SELECT count(*) FROM documents WHERE node_id=? "
        f"AND access_scope IN ({placeholders})",
        (record_id, *scopes),
    ).fetchone()
    return int(row[0]) if row else 0


def traverse_records(
    connection: sqlite3.Connection,
    source_ids: Sequence[str],
    *,
    direction: str = "outgoing",
    relation_kinds: Sequence[str] | None = None,
    owner: str | None = None,
    access_scopes: Sequence[str] = ("public",),
    max_depth: int = 2,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], float]:
    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError(f"unsupported traversal direction: {direction}")
    if not 1 <= max_depth <= 4:
        raise ValueError("max_depth must be from 1 through 4")
    seeds = tuple(dict.fromkeys(source_ids))
    if not seeds:
        return [], 0.0
    if len(seeds) > 32:
        raise ValueError("source_ids must contain at most 32 identifiers")
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return [], 0.0
    kinds = tuple(dict.fromkeys(relation_kinds or ()))
    scope_slots = ",".join("?" for _ in scopes)
    kind_clause = (
        f" AND r.relation_kind IN ({','.join('?' for _ in kinds)})" if kinds else ""
    )
    edge_filter = f"rr.access_scope IN ({scope_slots}){kind_clause}"
    edge_values: list[Any] = [*scopes, *kinds]
    edge_selects: list[str] = []
    values: list[Any] = []
    if direction in {"outgoing", "both"}:
        edge_selects.append(
            "SELECT r.id,r.from_id,r.to_id FROM relations r "
            f"JOIN records rr ON rr.id=r.id WHERE {edge_filter}"
        )
        values.extend(edge_values)
    if direction in {"incoming", "both"}:
        edge_selects.append(
            "SELECT r.id,r.to_id,r.from_id FROM relations r "
            f"JOIN records rr ON rr.id=r.id WHERE {edge_filter}"
        )
        values.extend(edge_values)
    seed_slots = ",".join("?" for _ in seeds)
    target_clauses = [
        "walk.depth<?",
        "target.node_class!='relation'",
        f"target.access_scope IN ({scope_slots})",
        "instr(walk.node_path,char(31)||target.id||char(31))=0",
    ]
    values.extend((*seeds, *scopes, max_depth, *scopes))
    if owner:
        target_clauses.append("target.repo=?")
        values.append(owner)
    values.extend((limit, offset))
    started = time.perf_counter()
    rows = connection.execute(
        "WITH RECURSIVE edges(relation_id,source_id,target_id) AS NOT MATERIALIZED ("
        + " UNION ALL ".join(edge_selects)
        + "),walk(source_id,current_id,depth,node_path,relation_path) AS ("
        "SELECT id,id,0,char(31)||id||char(31),'' FROM records "
        f"WHERE id IN ({seed_slots}) AND node_class!='relation' "
        f"AND access_scope IN ({scope_slots}) UNION ALL "
        "SELECT walk.source_id,target.id,walk.depth+1,"
        "walk.node_path||target.id||char(31),"
        "walk.relation_path||edges.relation_id||char(31) "
        "FROM walk JOIN edges ON edges.source_id=walk.current_id "
        "JOIN records target ON target.id=edges.target_id WHERE "
        + " AND ".join(target_clauses)
        + ") SELECT source_id,current_id,depth,node_path,relation_path FROM walk "
        "WHERE depth>0 ORDER BY depth,current_id,source_id,relation_path "
        "LIMIT ? OFFSET ?",
        tuple(values),
    ).fetchall()
    latency = (time.perf_counter() - started) * 1000
    path_rows: list[tuple[str, str, int, list[str], list[str]]] = []
    record_ids: set[str] = set()
    for row in rows:
        node_ids = [item for item in str(row[3]).split(chr(31)) if item]
        relation_ids = [item for item in str(row[4]).split(chr(31)) if item]
        record_ids.update(node_ids)
        record_ids.update(relation_ids)
        path_rows.append(
            (str(row[0]), str(row[1]), int(row[2]), node_ids, relation_ids)
        )
    records: dict[str, dict[str, Any]] = {}
    identifiers = sorted(record_ids)
    for batch in _batches(((item,) for item in identifiers), size=500):
        batch_ids = [str(item[0]) for item in batch]
        placeholders = ",".join("?" for _ in batch_ids)
        for row in connection.execute(
            f"SELECT id,payload_json FROM records WHERE id IN ({placeholders})",
            tuple(batch_ids),
        ):
            records[str(row[0])] = json.loads(row[1])
    hits: list[dict[str, Any]] = []
    for source_id, target_id, depth, node_ids, relation_ids in path_rows:
        target = records.get(target_id)
        if not target:
            continue
        path_relations = [
            {
                key: records[relation_id].get(key)
                for key in (
                    "id",
                    "relation_kind",
                    "from_id",
                    "to_id",
                    "scope",
                    "evidence_anchor_ids",
                    "evidence_class",
                    "confidence",
                    "provenance_ref",
                    "temporal_ref",
                    "trust_ref",
                )
            }
            for relation_id in relation_ids
            if relation_id in records
        ]
        anchors = sorted(
            {
                str(anchor)
                for relation in path_relations
                for anchor in relation.get("evidence_anchor_ids", [])
            }
        )
        path_id = hashlib.sha256(
            canonical_json(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_ids": relation_ids,
                }
            ).encode("utf-8")
        ).hexdigest()
        hits.append(
            {
                "source_id": source_id,
                "id": target_id,
                "repo": str(target["repo"]),
                "namespace": str(target["namespace"]),
                "node_class": str(target["node_class"]),
                "kind": str(target["kind"]),
                "source_record_ids": list(target.get("source_record_ids", [])),
                "anchor_ids": list(target.get("anchor_ids", [])) or anchors,
                "access": {"scope": str(target["access_scope"])},
                "depth": depth,
                "evidence_path": {
                    "path_id": path_id,
                    "source_id": source_id,
                    "target_id": target_id,
                    "depth": depth,
                    "nodes": [
                        {
                            key: records[node_id].get(key)
                            for key in (
                                "id",
                                "repo",
                                "namespace",
                                "node_class",
                                "kind",
                                "access_scope",
                            )
                        }
                        for node_id in node_ids
                        if node_id in records
                    ],
                    "relations": path_relations,
                    "anchor_ids": anchors,
                },
            }
        )
    return hits, latency


def search_documents_exact(
    connection: sqlite3.Connection,
    query: str,
    *,
    repo: str | None = None,
    node_class: str | None = None,
    kind: str | None = None,
    path: str | None = None,
    path_prefix: str | None = None,
    document_role: str | None = None,
    surface_state: str | None = None,
    access_scopes: Sequence[str] = ("public",),
    detail: str = "compact",
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return [], 0.0
    clauses = [f"access_scope IN ({','.join('?' for _ in scopes)})"]
    values: list[Any] = list(scopes)
    if repo:
        clauses.append("repo=?")
        values.append(repo)
    if node_class:
        clauses.append("node_class=?")
        values.append(node_class)
    if kind:
        clauses.append("kind=?")
        values.append(kind)
    if path:
        clauses.append("path=?")
        values.append(path)
    if path_prefix:
        clauses.append("path LIKE ? ESCAPE '\\'")
        escaped = (
            path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        values.append(f"{escaped}%")
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(documents)")
    }
    if document_role and "document_role" in columns:
        clauses.append("document_role=?")
        values.append(document_role)
    elif not document_role and "document_role" in columns:
        clauses.append("document_role!='evaluation_fixture'")
    elif not document_role:
        clauses.extend(
            (
                "path NOT LIKE '%retrieval-eval.%'",
                "path NOT LIKE '%retrieval_eval.%'",
                "path NOT LIKE '%/fixtures/%'",
            )
        )
    if surface_state and "surface_state" in columns:
        clauses.append("surface_state=?")
        values.append(surface_state)
    rows = _exact_union_rows(
        connection,
        table="documents",
        query=query,
        query_fields=("id", "node_id", "path", "label"),
        clauses=clauses,
        clause_values=values,
        order_by="repo,path,start_line,chunk_index,id",
        limit=limit,
        offset=offset,
    )
    return (
        [document_payload(row, detail=detail) for row in rows],
        (time.perf_counter() - started) * 1000,
    )


def search_documents_lexical(
    connection: sqlite3.Connection,
    query: str,
    *,
    repo: str | None = None,
    node_class: str | None = None,
    kind: str | None = None,
    path: str | None = None,
    path_prefix: str | None = None,
    document_role: str | None = None,
    surface_state: str | None = None,
    access_scopes: Sequence[str] = ("public",),
    operator: str = "AND",
    detail: str = "compact",
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    expression = _fts_expression(query, operator)
    scopes = tuple(dict.fromkeys(access_scopes))
    if not expression or not scopes:
        return [], 0.0
    fts_columns = [
        str(row[1]) for row in connection.execute("PRAGMA table_info(documents_fts)")
    ]
    match_expression = _scoped_fts_expression(
        expression,
        set(fts_columns),
        (
            ("repo", repo),
            ("node_class", node_class),
            ("kind", kind),
            ("document_role", document_role),
            ("surface_state", surface_state),
        ),
    )
    clauses = [f"d.access_scope IN ({','.join('?' for _ in scopes)})"]
    values: list[Any] = list(scopes)
    if repo:
        clauses.append("d.repo=?")
        values.append(repo)
    if node_class:
        clauses.append("d.node_class=?")
        values.append(node_class)
    if kind:
        clauses.append("d.kind=?")
        values.append(kind)
    if path:
        clauses.append("d.path=?")
        values.append(path)
    if path_prefix:
        clauses.append("d.path LIKE ? ESCAPE '\\'")
        escaped = (
            path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        values.append(f"{escaped}%")
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(documents)")
    }
    if document_role and "document_role" in columns:
        clauses.append("d.document_role=?")
        values.append(document_role)
    elif not document_role and "document_role" in columns:
        clauses.append("d.document_role!='evaluation_fixture'")
    elif not document_role:
        clauses.extend(
            (
                "d.path NOT LIKE '%retrieval-eval.%'",
                "d.path NOT LIKE '%retrieval_eval.%'",
                "d.path NOT LIKE '%/fixtures/%'",
            )
        )
    if surface_state and "surface_state" in columns:
        clauses.append("d.surface_state=?")
        values.append(surface_state)
    weights_by_column = {
        "id": 0.0,
        "repo": 0.0,
        "node_class": 0.0,
        "kind": 0.0,
        "path": 2.0,
        "label": 10.0,
        "document_role": 0.0,
        "surface_state": 0.0,
        "text": 1.0,
    }
    weights = ",".join(
        str(weights_by_column.get(column, 1.0)) for column in fts_columns
    )
    if "id" in fts_columns:
        statement = (
            "SELECT d.*,bm25(documents_fts," + weights + ") AS lexical_rank "
            "FROM documents_fts f JOIN documents d ON d.id=f.id "
            f"WHERE documents_fts MATCH ? AND {' AND '.join(clauses)} "
            "ORDER BY lexical_rank,d.id LIMIT ? OFFSET ?"
        )
        parameters = (match_expression, *values, limit, offset)
    else:
        statement = (
            "SELECT d.*,documents_fts.rank AS lexical_rank "
            "FROM documents_fts CROSS JOIN documents d "
            "ON d.rowid=documents_fts.rowid "
            "WHERE documents_fts MATCH ? AND documents_fts.rank MATCH ? AND "
            f"{' AND '.join(clauses)} "
            "ORDER BY documents_fts.rank,d.id LIMIT ? OFFSET ?"
        )
        parameters = (
            match_expression,
            f"bm25({weights})",
            *values,
            limit,
            offset,
        )
    rows = connection.execute(statement, parameters).fetchall()
    hits: list[dict[str, Any]] = []
    for row in rows:
        payload = document_payload(row, detail=detail)
        payload["lexical_rank"] = float(row["lexical_rank"])
        hits.append(payload)
    return hits, (time.perf_counter() - started) * 1000
