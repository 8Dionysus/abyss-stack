from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Neo4jStoreStatus:
    configured: bool
    uri: str | None
    user: str | None
    note: str


def describe_neo4j_store(uri: str | None, user: str | None) -> Neo4jStoreStatus:
    if not uri:
        return Neo4jStoreStatus(
            configured=False,
            uri=None,
            user=user,
            note="neo4j preview-only in this slice; no runtime projection attempted",
        )
    return Neo4jStoreStatus(
        configured=True,
        uri=uri,
        user=user,
        note="neo4j runtime projection is deferred; current sync route reports preview counts only",
    )
