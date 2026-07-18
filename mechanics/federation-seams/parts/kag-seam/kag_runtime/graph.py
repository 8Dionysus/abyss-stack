from __future__ import annotations

import copy
import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterable, Iterator

from .bundle import RetrievalBundle, canonical_json, write_json_atomic
from .transport import HttpJsonError, JsonHttpClient


SCHEMA_VERSION = "abyss-stack-repo-self-kag-neo4j-v1"
OWNER_SLICE_SCHEMA_VERSION = "abyss-stack-repo-self-kag-neo4j-owner-slices-v1"
DEFAULT_CHANNEL = "repo-self-current"


def _batches(
    records: Iterable[dict[str, Any]], size: int
) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for record in records:
        batch.append(record)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class Neo4jProjection:
    def __init__(
        self,
        client: JsonHttpClient,
        database: str = "neo4j",
        channel: str = DEFAULT_CHANNEL,
    ) -> None:
        if not channel.strip():
            raise ValueError("Neo4j projection channel must be non-empty")
        self.client = client
        self.database = database
        self.channel = channel

    def execute(
        self,
        statement: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[list[Any]]:
        response = self.client.request(
            "POST",
            f"/db/{self.database}/tx/commit",
            {
                "statements": [
                    {
                        "statement": statement,
                        "parameters": parameters or {},
                        "resultDataContents": ["row"],
                    }
                ]
            },
        )
        errors = response.get("errors")
        if isinstance(errors, list) and errors:
            message = "; ".join(str(item.get("message", item)) for item in errors)
            raise RuntimeError(f"Neo4j transaction failed: {message}")
        results = response.get("results")
        if not isinstance(results, list) or not results:
            return []
        data = results[0].get("data", [])
        return [item.get("row", []) for item in data if isinstance(item, dict)]

    def scalar(self, statement: str, parameters: dict[str, Any]) -> Any:
        rows = self.execute(statement, parameters)
        if not rows or not rows[0]:
            return None
        return rows[0][0]


def _owner_row(record: dict[str, Any]) -> dict[str, Any]:
    repo = record["repo"]
    return {
        "repo": str(repo["name"]),
        "namespace": str(repo["namespace"]),
        "owner_type": str(repo["owner_type"]),
        "git_ref": str(repo["git_ref"]),
        "source_index_digest": str(record["source_index_digest"]),
        "node_counts_json": canonical_json(record["node_counts"]),
        "relation_count": int(record["relation_count"]),
    }


def _node_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record["id"]),
        "repo": str(record["repo"]),
        "namespace": str(record["namespace"]),
        "node_class": str(record["node_class"]),
        "kind": str(record["kind"]),
        "source_record_ids": list(record["source_record_ids"]),
        "anchor_ids": list(record["anchor_ids"]),
        "access_scope": str(record["access_scope"]),
    }


def _relation_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record["id"]),
        "relation_kind": str(record["relation_kind"]),
        "from_id": str(record["from_id"]),
        "to_id": str(record["to_id"]),
        "source_repo": str(record["source_repo"]),
        "target_repo": str(record["target_repo"]),
        "scope": str(record["scope"]),
        "evidence_anchor_ids": list(record["evidence_anchor_ids"]),
        "evidence_class": str(record["evidence_class"]),
        "confidence": float(record["confidence"]),
        "temporal_ref": str(record["temporal_ref"]),
        "provenance_ref": str(record["provenance_ref"]),
        "trust_ref": str(record["trust_ref"]),
    }


def _external_row(record: dict[str, Any]) -> dict[str, Any]:
    identifier = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
    return {
        "id": f"external:{identifier}",
        "source_repo": str(record["source_repo"]),
        "source_anchor_id": str(record["source_anchor_id"]),
        "target_repo": str(record.get("target_repo", "")),
        "target_ref": str(record["target_ref"]),
        "reference_kind": str(record["reference_kind"]),
    }


def _owner_inputs(bundle: RetrievalBundle) -> dict[str, dict[str, Any]]:
    inputs: dict[str, dict[str, Any]] = {}
    for raw in bundle.manifest.get("canonical_inputs", []):
        if not isinstance(raw, dict) or not isinstance(raw.get("repo"), dict):
            raise RuntimeError("retrieval canonical input is invalid")
        owner = str(raw["repo"].get("name") or "")
        if not owner or owner in inputs:
            raise RuntimeError("retrieval canonical input owners are invalid")
        inputs[owner] = copy.deepcopy(raw)
    return inputs


def _semantic_owner_input(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result.pop("distribution_identity", None)
    return result


def _owner_slice_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json(_semantic_owner_input(value)).encode("utf-8")
    ).hexdigest()


def _pair_key(source_repo: str, target_repo: str) -> str:
    return hashlib.sha256(
        f"{source_repo}\0{target_repo}".encode("utf-8")
    ).hexdigest()


def _relation_slice_digest(
    records: list[dict[str, Any]],
    source_slice: str,
    target_slice: str,
) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "source_slice": source_slice,
                "target_slice": target_slice,
                "records": records,
            }
        ).encode("utf-8")
    ).hexdigest()


def _external_slice_digest(
    records: list[dict[str, Any]],
    source_slice: str,
    target_repo: str,
) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "source_slice": source_slice,
                "target_repo": target_repo,
                "records": records,
            }
        ).encode("utf-8")
    ).hexdigest()


def _read_owner_slice_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != OWNER_SLICE_SCHEMA_VERSION
        or not isinstance(payload.get("owners"), dict)
        or not isinstance(payload.get("relations"), dict)
        or not isinstance(payload.get("external_references"), dict)
    ):
        return {}
    return payload


def _current_digest(graph: Neo4jProjection) -> str | None:
    value = graph.scalar(
        "MATCH (p:AoAKagProjection {name: $channel}) RETURN p.current_digest",
        {"channel": getattr(graph, "channel", DEFAULT_CHANNEL)},
    )
    return str(value) if value else None


def _previous_digest(graph: Neo4jProjection) -> str | None:
    value = graph.scalar(
        "MATCH (p:AoAKagProjection {name: $channel}) RETURN p.previous_digest",
        {"channel": getattr(graph, "channel", DEFAULT_CHANNEL)},
    )
    return str(value) if value else None


def _retained_digests(graph: Neo4jProjection) -> list[str]:
    value = graph.scalar(
        "MATCH (p:AoAKagProjection) "
        "UNWIND [p.current_digest,p.previous_digest] AS digest "
        "WITH DISTINCT digest WHERE digest IS NOT NULL AND digest <> '' "
        "RETURN collect(digest)",
        {},
    )
    if not isinstance(value, list):
        raise RuntimeError("Neo4j projection channel inventory is missing")
    return sorted(str(item) for item in value if item)


def _load_projection(
    bundle: RetrievalBundle,
    *,
    graph: Neo4jProjection,
    projection: str,
    totals: dict[str, int],
    batch_size: int,
    progress: Callable[[str, int, int], None] | None,
) -> None:
    completed = 0
    for batch in _batches(
        (_owner_row(item) for item in bundle.records("owners")), batch_size
    ):
        graph.execute(
            "UNWIND $rows AS row "
            "MERGE (o:AoAKagOwner {projection_digest: $projection, repo: row.repo}) "
            "SET o.namespace = row.namespace, o.owner_type = row.owner_type, "
            "o.git_ref = row.git_ref, o.source_index_digest = row.source_index_digest, "
            "o.node_counts_json = row.node_counts_json, o.relation_count = row.relation_count",
            {"projection": projection, "rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("owners", completed, totals["owners"])

    completed = 0
    for batch in _batches(
        (_node_row(item) for item in bundle.records("nodes")), batch_size
    ):
        graph.execute(
            "UNWIND $rows AS row "
            "MERGE (n:AoAKagNode {projection_digest: $projection, id: row.id}) "
            "SET n.repo = row.repo, n.namespace = row.namespace, "
            "n.node_class = row.node_class, n.kind = row.kind, "
            "n.source_record_ids = row.source_record_ids, n.anchor_ids = row.anchor_ids, "
            "n.access_scope = row.access_scope "
            "WITH n, row "
            "MATCH (o:AoAKagOwner {projection_digest: $projection, repo: row.repo}) "
            "MERGE (n)-[:AOA_KAG_OWNED_BY {projection_digest: $projection}]->(o)",
            {"projection": projection, "rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("nodes", completed, totals["nodes"])

    completed = 0
    for batch in _batches(
        (_relation_row(item) for item in bundle.records("relations")),
        batch_size,
    ):
        graph.execute(
            "UNWIND $rows AS row "
            "MATCH (source:AoAKagNode {projection_digest: $projection, id: row.from_id}) "
            "MATCH (target:AoAKagNode {projection_digest: $projection, id: row.to_id}) "
            "MERGE (source)-[r:AOA_KAG_RELATION {projection_digest: $projection, id: row.id}]->(target) "
            "SET r.relation_kind = row.relation_kind, r.source_repo = row.source_repo, "
            "r.target_repo = row.target_repo, r.scope = row.scope, "
            "r.evidence_anchor_ids = row.evidence_anchor_ids, "
            "r.evidence_class = row.evidence_class, r.confidence = row.confidence, "
            "r.temporal_ref = row.temporal_ref, r.provenance_ref = row.provenance_ref, "
            "r.trust_ref = row.trust_ref",
            {"projection": projection, "rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("relations", completed, totals["relations"])

    completed = 0
    for batch in _batches(
        (_external_row(item) for item in bundle.records("external_references")),
        batch_size,
    ):
        graph.execute(
            "UNWIND $rows AS row "
            "MATCH (source:AoAKagNode {projection_digest: $projection, id: row.source_anchor_id}) "
            "MERGE (target:AoAKagExternal {projection_digest: $projection, id: row.id}) "
            "SET target.target_repo = row.target_repo, target.target_ref = row.target_ref, "
            "target.reference_kind = row.reference_kind "
            "MERGE (source)-[r:AOA_KAG_EXTERNAL_REFERENCE "
            "{projection_digest: $projection, id: row.id}]->(target) "
            "SET r.source_repo = row.source_repo, r.reference_kind = row.reference_kind",
            {"projection": projection, "rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress(
                "external_references",
                completed,
                totals["external_references"],
            )


def _cleanup_projections(
    graph: Neo4jProjection,
    *,
    keep: list[str],
    batch_size: int,
) -> None:
    for label in ("AoAKagNode", "AoAKagOwner", "AoAKagExternal"):
        statement = (
            f"MATCH (n:{label}) "
            "WHERE n.projection_digest IS NOT NULL AND NOT n.projection_digest IN $keep "
            "WITH n LIMIT $limit DETACH DELETE n RETURN count(*)"
        )
        while True:
            for attempt in range(3):
                try:
                    removed = int(
                        graph.scalar(
                            statement,
                            {"keep": keep, "limit": batch_size},
                        )
                        or 0
                    )
                    break
                except HttpJsonError as exc:
                    if exc.status not in {0, 502, 503, 504} or attempt == 2:
                        raise
                    time.sleep(2**attempt)
            if removed == 0:
                break


def _owner_slice_counts(
    graph: Neo4jProjection,
    state: dict[str, Any],
) -> dict[str, int]:
    owner_slices = [
        str(item["slice_digest"])
        for item in state["owners"].values()
    ]
    relation_slices = [
        str(item["slice_digest"])
        for item in state["relations"].values()
    ]
    external_slices = [
        str(item["slice_digest"])
        for item in state["external_references"].values()
    ]
    queries = {
        "owners": (
            "MATCH (n:AoAKagOwnerSlice) "
            "WHERE n.slice_digest IN $slices RETURN count(n)",
            owner_slices,
        ),
        "nodes": (
            "MATCH (n:AoAKagNodeSlice) "
            "WHERE n.slice_digest IN $slices RETURN count(n)",
            owner_slices,
        ),
        "relations": (
            "MATCH ()-[r:AOA_KAG_RELATION_SLICE]->() "
            "WHERE r.slice_digest IN $slices RETURN count(r)",
            relation_slices,
        ),
        "external_references": (
            "MATCH ()-[r:AOA_KAG_EXTERNAL_REFERENCE_SLICE]->() "
            "WHERE r.slice_digest IN $slices RETURN count(r)",
            external_slices,
        ),
    }
    return {
        key: int(graph.scalar(statement, {"slices": slices}) or 0)
        for key, (statement, slices) in queries.items()
    }


def materialize_owner_slices(
    bundle: RetrievalBundle,
    *,
    graph: Neo4jProjection,
    state_path: Path,
    affected_owners: Iterable[str] = (),
    batch_size: int = 1000,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    inputs = _owner_inputs(bundle)
    previous = _read_owner_slice_state(state_path)
    previous_owners = (
        previous.get("owners") if isinstance(previous.get("owners"), dict) else {}
    )
    selected = {str(item) for item in affected_owners if str(item)}
    if not selected:
        selected = set(inputs)
    unknown = sorted(selected - set(inputs))
    if unknown:
        raise RuntimeError(
            "affected graph owners are absent from the bundle: "
            + ", ".join(unknown)
        )
    if previous and set(previous_owners) != set(inputs):
        raise RuntimeError("graph owner membership changed; bootstrap all owner slices")
    changed = {
        owner
        for owner, owner_input in inputs.items()
        if owner not in previous_owners
        or _semantic_owner_input(
            dict(previous_owners[owner].get("canonical_input") or {})
        )
        != _semantic_owner_input(owner_input)
    }
    missing = sorted(changed - selected)
    if missing:
        raise RuntimeError(
            "affected graph owner set omits changed canonical inputs: "
            + ", ".join(missing)
        )
    if not previous and selected != set(inputs):
        raise RuntimeError(
            "graph owner slices require a full owner bootstrap before incremental use"
        )

    owner_records: dict[str, dict[str, Any]] = {}
    for record in bundle.records("owners"):
        owner = str((record.get("repo") or {}).get("name") or "")
        if owner in selected:
            owner_records[owner] = record
    if set(owner_records) != selected:
        raise RuntimeError("graph owner records do not cover the affected owner set")
    nodes: dict[str, list[dict[str, Any]]] = {owner: [] for owner in selected}
    for record in bundle.records("nodes"):
        owner = str(record.get("repo") or "")
        if owner in nodes:
            nodes[owner].append(record)

    owner_states: dict[str, dict[str, Any]] = {}
    for owner, owner_input in sorted(inputs.items()):
        if owner in selected:
            node_count = len(nodes[owner])
        else:
            previous_entry = previous_owners.get(owner)
            if not isinstance(previous_entry, dict):
                raise RuntimeError(f"graph owner state is missing: {owner}")
            node_count = int(previous_entry.get("node_count") or 0)
        owner_states[owner] = {
            "canonical_input": copy.deepcopy(owner_input),
            "slice_digest": _owner_slice_digest(owner_input),
            "node_count": node_count,
        }

    relation_groups: dict[str, list[dict[str, Any]]] = {}
    relation_pairs: dict[str, tuple[str, str]] = {}
    for record in bundle.records("relations"):
        source_repo = str(record.get("source_repo") or "")
        target_repo = str(record.get("target_repo") or "")
        if not {source_repo, target_repo}.intersection(selected):
            continue
        key = _pair_key(source_repo, target_repo)
        relation_pairs[key] = (source_repo, target_repo)
        relation_groups.setdefault(key, []).append(record)
    external_groups: dict[str, list[dict[str, Any]]] = {}
    external_pairs: dict[str, tuple[str, str]] = {}
    for record in bundle.records("external_references"):
        source_repo = str(record.get("source_repo") or "")
        target_repo = str(record.get("target_repo") or "")
        if not {source_repo, target_repo}.intersection(selected):
            continue
        key = _pair_key(source_repo, target_repo)
        external_pairs[key] = (source_repo, target_repo)
        external_groups.setdefault(key, []).append(record)

    previous_relations = (
        previous.get("relations") if isinstance(previous.get("relations"), dict) else {}
    )
    relation_states = {
        key: copy.deepcopy(value)
        for key, value in previous_relations.items()
        if isinstance(value, dict)
        and not {
            str(value.get("source_repo") or ""),
            str(value.get("target_repo") or ""),
        }.intersection(selected)
    }
    for key, records in sorted(relation_groups.items()):
        source_repo, target_repo = relation_pairs[key]
        relation_states[key] = {
            "source_repo": source_repo,
            "target_repo": target_repo,
            "source_slice": owner_states[source_repo]["slice_digest"],
            "target_slice": owner_states[target_repo]["slice_digest"],
            "slice_digest": _relation_slice_digest(
                records,
                owner_states[source_repo]["slice_digest"],
                owner_states[target_repo]["slice_digest"],
            ),
            "record_count": len(records),
        }
    previous_external = (
        previous.get("external_references")
        if isinstance(previous.get("external_references"), dict)
        else {}
    )
    external_states = {
        key: copy.deepcopy(value)
        for key, value in previous_external.items()
        if isinstance(value, dict)
        and not {
            str(value.get("source_repo") or ""),
            str(value.get("target_repo") or ""),
        }.intersection(selected)
    }
    for key, records in sorted(external_groups.items()):
        source_repo, target_repo = external_pairs[key]
        external_states[key] = {
            "source_repo": source_repo,
            "target_repo": target_repo,
            "source_slice": owner_states[source_repo]["slice_digest"],
            "slice_digest": _external_slice_digest(
                records,
                owner_states[source_repo]["slice_digest"],
                target_repo,
            ),
            "record_count": len(records),
        }

    graph.execute(
        "CREATE INDEX aoa_kag_node_slice_identity IF NOT EXISTS "
        "FOR (n:AoAKagNodeSlice) ON (n.slice_digest, n.id)"
    )
    graph.execute(
        "CREATE INDEX aoa_kag_owner_slice_identity IF NOT EXISTS "
        "FOR (n:AoAKagOwnerSlice) ON (n.slice_digest, n.repo)"
    )
    completed = 0
    owner_rows = []
    for owner in sorted(selected):
        row = _owner_row(owner_records[owner])
        row["slice_digest"] = owner_states[owner]["slice_digest"]
        owner_rows.append(row)
    for batch in _batches(owner_rows, batch_size):
        graph.execute(
            "UNWIND $rows AS row "
            "MERGE (o:AoAKagOwnerSlice {slice_digest: row.slice_digest, repo: row.repo}) "
            "SET o.namespace = row.namespace, o.owner_type = row.owner_type, "
            "o.git_ref = row.git_ref, o.source_index_digest = row.source_index_digest, "
            "o.node_counts_json = row.node_counts_json, o.relation_count = row.relation_count",
            {"rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("owners", completed, len(owner_rows))

    node_rows = []
    for owner in sorted(selected):
        for record in nodes[owner]:
            row = _node_row(record)
            row["slice_digest"] = owner_states[owner]["slice_digest"]
            node_rows.append(row)
    completed = 0
    for batch in _batches(node_rows, batch_size):
        graph.execute(
            "UNWIND $rows AS row "
            "MERGE (n:AoAKagNodeSlice {slice_digest: row.slice_digest, id: row.id}) "
            "SET n.repo = row.repo, n.namespace = row.namespace, "
            "n.node_class = row.node_class, n.kind = row.kind, "
            "n.source_record_ids = row.source_record_ids, n.anchor_ids = row.anchor_ids, "
            "n.access_scope = row.access_scope "
            "WITH n, row "
            "MATCH (o:AoAKagOwnerSlice {slice_digest: row.slice_digest, repo: row.repo}) "
            "MERGE (n)-[:AOA_KAG_OWNED_BY_SLICE {slice_digest: row.slice_digest}]->(o)",
            {"rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("nodes", completed, len(node_rows))

    relation_rows = []
    for key, records in sorted(relation_groups.items()):
        state = relation_states[key]
        for record in records:
            row = _relation_row(record)
            row.update(
                {
                    "source_slice": state["source_slice"],
                    "target_slice": state["target_slice"],
                    "slice_digest": state["slice_digest"],
                }
            )
            relation_rows.append(row)
    completed = 0
    for batch in _batches(relation_rows, batch_size):
        graph.execute(
            "UNWIND $rows AS row "
            "MATCH (source:AoAKagNodeSlice {slice_digest: row.source_slice, id: row.from_id}) "
            "MATCH (target:AoAKagNodeSlice {slice_digest: row.target_slice, id: row.to_id}) "
            "MERGE (source)-[r:AOA_KAG_RELATION_SLICE "
            "{slice_digest: row.slice_digest, id: row.id}]->(target) "
            "SET r.relation_kind = row.relation_kind, r.source_repo = row.source_repo, "
            "r.target_repo = row.target_repo, r.scope = row.scope, "
            "r.evidence_anchor_ids = row.evidence_anchor_ids, "
            "r.evidence_class = row.evidence_class, r.confidence = row.confidence, "
            "r.temporal_ref = row.temporal_ref, r.provenance_ref = row.provenance_ref, "
            "r.trust_ref = row.trust_ref",
            {"rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("relations", completed, len(relation_rows))

    external_rows = []
    for key, records in sorted(external_groups.items()):
        state = external_states[key]
        for record in records:
            row = _external_row(record)
            row.update(
                {
                    "source_slice": state["source_slice"],
                    "slice_digest": state["slice_digest"],
                }
            )
            external_rows.append(row)
    completed = 0
    for batch in _batches(external_rows, batch_size):
        graph.execute(
            "UNWIND $rows AS row "
            "MATCH (source:AoAKagNodeSlice "
            "{slice_digest: row.source_slice, id: row.source_anchor_id}) "
            "MERGE (target:AoAKagExternalSlice "
            "{slice_digest: row.slice_digest, id: row.id}) "
            "SET target.target_repo = row.target_repo, target.target_ref = row.target_ref, "
            "target.reference_kind = row.reference_kind "
            "MERGE (source)-[r:AOA_KAG_EXTERNAL_REFERENCE_SLICE "
            "{slice_digest: row.slice_digest, id: row.id}]->(target) "
            "SET r.source_repo = row.source_repo, r.target_repo = row.target_repo, "
            "r.reference_kind = row.reference_kind",
            {"rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("external_references", completed, len(external_rows))

    state = {
        "schema_version": OWNER_SLICE_SCHEMA_VERSION,
        "storage_mode": "owner_slices",
        "database": graph.database,
        "channel": getattr(graph, "channel", DEFAULT_CHANNEL),
        "bundle_digest": bundle.bundle_digest,
        "projection_digest": bundle.projection_digest,
        "federation_digest": bundle.federation_digest,
        "owners": owner_states,
        "relations": relation_states,
        "external_references": external_states,
    }
    expected = {
        "owners": len(owner_states),
        "nodes": sum(int(item["node_count"]) for item in owner_states.values()),
        "relations": sum(
            int(item["record_count"]) for item in relation_states.values()
        ),
        "external_references": sum(
            int(item["record_count"]) for item in external_states.values()
        ),
    }
    observed = _owner_slice_counts(graph, state)
    if observed != expected:
        raise RuntimeError(
            f"Neo4j owner-slice counts mismatch: {observed} != {expected}"
        )
    current = _current_digest(graph)
    graph.execute(
        "MERGE (p:AoAKagProjection {name: $channel}) "
        "SET p.previous_digest = p.current_digest, p.current_digest = $projection, "
        "p.bundle_digest = $bundle, p.federation_digest = $federation, "
        "p.storage_mode = 'owner_slices', p.owner_count = $owners, "
        "p.node_count = $nodes, p.relation_count = $relations, "
        "p.external_reference_count = $external",
        {
            "channel": getattr(graph, "channel", DEFAULT_CHANNEL),
            "projection": bundle.projection_digest,
            "bundle": bundle.bundle_digest,
            "federation": bundle.federation_digest,
            "owners": expected["owners"],
            "nodes": expected["nodes"],
            "relations": expected["relations"],
            "external": expected["external_references"],
        },
    )
    state_path = state_path.resolve()
    if previous and previous != state:
        write_json_atomic(
            state_path.with_name(f"{state_path.stem}.last-good{state_path.suffix}"),
            previous,
        )
    write_json_atomic(state_path, state)
    return {
        "schema_version": OWNER_SLICE_SCHEMA_VERSION,
        "storage_mode": "owner_slices",
        "database": graph.database,
        "channel": getattr(graph, "channel", DEFAULT_CHANNEL),
        "state_path": str(state_path),
        "projection_digest": bundle.projection_digest,
        "previous_projection_digest": current,
        "affected_owners": sorted(selected),
        "changed_owners": sorted(changed),
        "reused_owner_slices": sorted(set(inputs) - selected),
        "owner_slices": {
            owner: str(item["slice_digest"])
            for owner, item in sorted(owner_states.items())
        },
        "relation_slices": sorted(
            str(item["slice_digest"]) for item in relation_states.values()
        ),
        "external_reference_slices": sorted(
            str(item["slice_digest"]) for item in external_states.values()
        ),
        "counts": observed,
    }


def check_owner_slices(
    bundle: RetrievalBundle,
    *,
    graph: Neo4jProjection,
    state_path: Path,
) -> dict[str, Any]:
    state = _read_owner_slice_state(state_path.resolve())
    if not state:
        raise RuntimeError("graph owner-slice state is missing or invalid")
    if state.get("projection_digest") != bundle.projection_digest:
        raise RuntimeError("graph owner-slice projection identity mismatch")
    inputs = _owner_inputs(bundle)
    if set(state["owners"]) != set(inputs):
        raise RuntimeError("graph owner-slice membership mismatch")
    current = _current_digest(graph)
    if current != bundle.projection_digest:
        raise RuntimeError(
            f"Neo4j current projection is {current}, expected {bundle.projection_digest}"
        )
    observed = _owner_slice_counts(graph, state)
    expected = {
        "owners": len(state["owners"]),
        "nodes": sum(
            int(item["node_count"]) for item in state["owners"].values()
        ),
        "relations": sum(
            int(item["record_count"]) for item in state["relations"].values()
        ),
        "external_references": sum(
            int(item["record_count"])
            for item in state["external_references"].values()
        ),
    }
    if observed != expected:
        raise RuntimeError(
            f"Neo4j owner-slice counts mismatch: {observed} != {expected}"
        )
    return {
        "schema_version": OWNER_SLICE_SCHEMA_VERSION,
        "storage_mode": "owner_slices",
        "database": graph.database,
        "channel": getattr(graph, "channel", DEFAULT_CHANNEL),
        "state_path": str(state_path.resolve()),
        "projection_digest": bundle.projection_digest,
        "owner_slices": {
            owner: str(item["slice_digest"])
            for owner, item in sorted(state["owners"].items())
        },
        "relation_slices": sorted(
            str(item["slice_digest"]) for item in state["relations"].values()
        ),
        "external_reference_slices": sorted(
            str(item["slice_digest"])
            for item in state["external_references"].values()
        ),
        "counts": observed,
    }


def owner_slice_rollback_candidate(
    *,
    graph: Neo4jProjection,
    state_path: Path,
) -> dict[str, Any]:
    current = _read_owner_slice_state(state_path.resolve())
    last_good_path = state_path.resolve().with_name(
        f"{state_path.stem}.last-good{state_path.suffix}"
    )
    candidate = _read_owner_slice_state(last_good_path)
    if not current or not candidate:
        raise RuntimeError("graph owner slices have no last-good rollback state")
    observed = _owner_slice_counts(graph, candidate)
    expected = {
        "owners": len(candidate["owners"]),
        "nodes": sum(
            int(item["node_count"]) for item in candidate["owners"].values()
        ),
        "relations": sum(
            int(item["record_count"]) for item in candidate["relations"].values()
        ),
        "external_references": sum(
            int(item["record_count"])
            for item in candidate["external_references"].values()
        ),
    }
    if observed != expected:
        raise RuntimeError(
            f"graph last-good owner-slice counts mismatch: {observed} != {expected}"
        )
    return {
        "candidate": candidate,
        "current": current,
        "last_good_path": last_good_path,
        "projection_digest": str(candidate.get("projection_digest") or ""),
        "bundle_digest": str(candidate.get("bundle_digest") or ""),
        "federation_digest": str(candidate.get("federation_digest") or ""),
        "counts": observed,
    }


def rollback_owner_slices(
    *,
    graph: Neo4jProjection,
    state_path: Path,
) -> dict[str, Any]:
    prepared = owner_slice_rollback_candidate(
        graph=graph,
        state_path=state_path,
    )
    candidate = prepared["candidate"]
    graph.execute(
        "MERGE (p:AoAKagProjection {name: $channel}) "
        "SET p.previous_digest = p.current_digest, p.current_digest = $projection, "
        "p.bundle_digest = $bundle, p.federation_digest = $federation, "
        "p.storage_mode = 'owner_slices', p.owner_count = $owners, "
        "p.node_count = $nodes, p.relation_count = $relations, "
        "p.external_reference_count = $external",
        {
            "channel": getattr(graph, "channel", DEFAULT_CHANNEL),
            "projection": prepared["projection_digest"],
            "bundle": prepared["bundle_digest"],
            "federation": prepared["federation_digest"],
            "owners": prepared["counts"]["owners"],
            "nodes": prepared["counts"]["nodes"],
            "relations": prepared["counts"]["relations"],
            "external": prepared["counts"]["external_references"],
        },
    )
    write_json_atomic(state_path.resolve(), candidate)
    write_json_atomic(prepared["last_good_path"], prepared["current"])
    return {
        "schema_version": OWNER_SLICE_SCHEMA_VERSION,
        "storage_mode": "owner_slices",
        "database": graph.database,
        "channel": getattr(graph, "channel", DEFAULT_CHANNEL),
        "state_path": str(state_path.resolve()),
        "projection_digest": prepared["projection_digest"],
        "bundle_digest": prepared["bundle_digest"],
        "federation_digest": prepared["federation_digest"],
        "owner_slices": {
            owner: str(item["slice_digest"])
            for owner, item in sorted(candidate["owners"].items())
        },
        "relation_slices": sorted(
            str(item["slice_digest"])
            for item in candidate["relations"].values()
        ),
        "external_reference_slices": sorted(
            str(item["slice_digest"])
            for item in candidate["external_references"].values()
        ),
        "counts": prepared["counts"],
        "rollback": True,
    }


def materialize(
    bundle: RetrievalBundle,
    *,
    graph: Neo4jProjection,
    batch_size: int = 1000,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    projection = bundle.projection_digest
    current = _current_digest(graph)
    previous = _previous_digest(graph) if current == projection else current
    graph.execute(
        "CREATE INDEX aoa_kag_node_identity IF NOT EXISTS "
        "FOR (n:AoAKagNode) ON (n.projection_digest, n.id)"
    )
    graph.execute(
        "CREATE INDEX aoa_kag_owner_identity IF NOT EXISTS "
        "FOR (n:AoAKagOwner) ON (n.projection_digest, n.repo)"
    )

    expected = {
        key: int(bundle.manifest["files"][key]["record_count"])
        for key in ("owners", "nodes", "relations", "external_references")
    }
    observed = _counts(graph, projection) if current == projection else {}
    if observed != expected:
        _load_projection(
            bundle,
            graph=graph,
            projection=projection,
            totals=expected,
            batch_size=batch_size,
            progress=progress,
        )
        observed = _counts(graph, projection)
    if observed != expected:
        raise RuntimeError(
            f"Neo4j projection counts mismatch: {observed} != {expected}"
        )

    if current != projection:
        graph.execute(
            "MERGE (p:AoAKagProjection {name: $channel}) "
            "SET p.previous_digest = p.current_digest, p.current_digest = $projection, "
            "p.bundle_digest = $bundle, p.federation_digest = $federation, "
            "p.owner_count = $owners, p.node_count = $nodes, "
            "p.relation_count = $relations, p.external_reference_count = $external",
            {
                "channel": getattr(graph, "channel", DEFAULT_CHANNEL),
                "projection": projection,
                "bundle": bundle.bundle_digest,
                "federation": bundle.federation_digest,
                "owners": expected["owners"],
                "nodes": expected["nodes"],
                "relations": expected["relations"],
                "external": expected["external_references"],
            },
        )
    keep = list(
        dict.fromkeys(
            item for item in (projection, previous, *_retained_digests(graph)) if item
        )
    )
    _cleanup_projections(graph, keep=keep, batch_size=batch_size)
    return {
        "schema_version": SCHEMA_VERSION,
        "database": graph.database,
        "channel": getattr(graph, "channel", DEFAULT_CHANNEL),
        "projection_digest": projection,
        "previous_projection_digest": previous,
        "retained_projection_digests": keep,
        "counts": observed,
    }


def _counts(graph: Neo4jProjection, projection: str) -> dict[str, int]:
    queries = {
        "owners": "MATCH (n:AoAKagOwner {projection_digest: $projection}) RETURN count(n)",
        "nodes": "MATCH (n:AoAKagNode {projection_digest: $projection}) RETURN count(n)",
        "relations": "MATCH ()-[r:AOA_KAG_RELATION {projection_digest: $projection}]->() RETURN count(r)",
        "external_references": "MATCH ()-[r:AOA_KAG_EXTERNAL_REFERENCE {projection_digest: $projection}]->() RETURN count(r)",
    }
    return {
        key: int(graph.scalar(query, {"projection": projection}) or 0)
        for key, query in queries.items()
    }


def check(bundle: RetrievalBundle, *, graph: Neo4jProjection) -> dict[str, Any]:
    projection = bundle.projection_digest
    current = _current_digest(graph)
    if current != projection:
        raise RuntimeError(
            f"Neo4j current projection is {current}, expected {projection}"
        )
    counts = _counts(graph, projection)
    expected = {
        key: int(bundle.manifest["files"][key]["record_count"]) for key in counts
    }
    if counts != expected:
        raise RuntimeError(f"Neo4j projection counts mismatch: {counts} != {expected}")
    return {
        "schema_version": SCHEMA_VERSION,
        "database": graph.database,
        "channel": getattr(graph, "channel", DEFAULT_CHANNEL),
        "projection_digest": projection,
        "counts": counts,
    }


def search_multihop(
    *,
    graph: Neo4jProjection,
    projection: str,
    source_id: str,
    first_relation: str,
    second_relation: str,
    source_path: str,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], float, float]:
    started = time.perf_counter()
    rows = graph.execute(
        "MATCH (source:AoAKagNode {projection_digest:$projection,id:$source_id}) "
        "-[r1:AOA_KAG_RELATION]->(middle:AoAKagNode)"
        "-[r2:AOA_KAG_RELATION]->(target:AoAKagNode) "
        "WHERE r1.projection_digest=$projection AND r2.projection_digest=$projection "
        "AND r1.relation_kind=$first AND r2.relation_kind=$second "
        "RETURN target.id,target.repo,target.source_record_ids,target.anchor_ids,"
        "target.access_scope,r1.id,r1.evidence_anchor_ids,r1.provenance_ref,"
        "r1.trust_ref,r2.id,r2.evidence_anchor_ids,r2.provenance_ref,r2.trust_ref "
        "ORDER BY target.id LIMIT $limit",
        {
            "projection": projection,
            "source_id": source_id,
            "first": first_relation,
            "second": second_relation,
            "limit": limit,
        },
    )
    latency = (time.perf_counter() - started) * 1000
    hits_by_id: dict[str, dict[str, Any]] = {}
    complete = 0
    for row in rows:
        edges = (
            {
                "id": row[5],
                "anchors": row[6],
                "provenance": row[7],
                "trust": row[8],
            },
            {
                "id": row[9],
                "anchors": row[10],
                "provenance": row[11],
                "trust": row[12],
            },
        )
        chain_complete = bool(
            row[1]
            and row[2]
            and row[4]
            and all(
                edge["id"] and edge["anchors"] and edge["provenance"] and edge["trust"]
                for edge in edges
            )
        )
        if row[0] in hits_by_id:
            continue
        complete += int(chain_complete)
        hits_by_id[row[0]] = {
            "id": row[0],
            "payload": {
                "id": row[0],
                "repo": row[1],
                "path": source_path,
                "locator": {"source_id": source_id},
                "source_record_ids": row[2],
                "anchor_ids": row[3]
                or [anchor for edge in edges for anchor in edge["anchors"]],
                "provenance_ref": edges[0]["provenance"],
                "trust_ref": edges[0]["trust"],
                "freshness": {"projection_digest": projection},
                "access": {"scope": row[4]},
                "evidence_chain": edges,
            },
        }
    hits = list(hits_by_id.values())
    return hits, latency, complete / max(len(hits), 1)


def traverse(
    *,
    graph: Neo4jProjection,
    projection: str,
    owner_slice_state: dict[str, Any] | None = None,
    source_ids: list[str],
    direction: str = "outgoing",
    relation_kinds: list[str] | None = None,
    owner: str | None = None,
    access_scopes: list[str] | None = None,
    max_depth: int = 2,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], float]:
    """Traverse a bounded simple path set without exposing Cypher to callers."""
    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError(f"unsupported traversal direction: {direction}")
    if not 1 <= max_depth <= 4:
        raise ValueError("max_depth must be from 1 through 4")
    if not source_ids:
        return [], 0.0
    if len(source_ids) > 32:
        raise ValueError("source_ids must contain at most 32 identifiers")
    scopes = list(dict.fromkeys(access_scopes or ["public"]))
    if not scopes:
        return [], 0.0

    owner_scoped = (
        isinstance(owner_slice_state, dict)
        and owner_slice_state.get("storage_mode") == "owner_slices"
    )
    relation_type = (
        "AOA_KAG_RELATION_SLICE" if owner_scoped else "AOA_KAG_RELATION"
    )
    node_label = "AoAKagNodeSlice" if owner_scoped else "AoAKagNode"
    if direction == "outgoing":
        pattern = f"(source)-[:{relation_type}*1..{max_depth}]->(target)"
    elif direction == "incoming":
        pattern = f"(source)<-[:{relation_type}*1..{max_depth}]-(target)"
    else:
        pattern = f"(source)-[:{relation_type}*1..{max_depth}]-(target)"

    conditions = ["all(n IN nodes(p) WHERE n.access_scope IN $access_scopes)"]
    if owner_scoped:
        conditions.extend(
            (
                "all(r IN relationships(p) WHERE r.slice_digest IN $relation_slices)",
                "all(n IN nodes(p) WHERE n.slice_digest IN $owner_slices)",
                "all(n IN nodes(p) WHERE single(m IN nodes(p) "
                "WHERE m.id = n.id AND m.slice_digest = n.slice_digest))",
            )
        )
        source_identity = (
            "WHERE source.id IN $source_ids "
            "AND source.slice_digest IN $owner_slices "
            "AND source.access_scope IN $access_scopes "
        )
    else:
        conditions.extend(
            (
                "all(r IN relationships(p) WHERE r.projection_digest=$projection)",
                "all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))",
            )
        )
        source_identity = (
            "WHERE source.id IN $source_ids "
            "AND source.access_scope IN $access_scopes "
        )
    if relation_kinds:
        conditions.append(
            "all(r IN relationships(p) WHERE r.relation_kind IN $relation_kinds)"
        )
    if owner:
        conditions.append("target.repo=$owner")

    started = time.perf_counter()
    source_match = (
        f"MATCH (source:{node_label}) "
        if owner_scoped
        else "MATCH (source:AoAKagNode {projection_digest:$projection}) "
    )
    query = (
        source_match
        + source_identity
        + f"MATCH p={pattern} "
        + f"WHERE {' AND '.join(conditions)} "
        + "RETURN source.id,target.id,target.repo,target.namespace,target.node_class,"
        "target.kind,target.source_record_ids,target.anchor_ids,target.access_scope,"
        "length(p),"
        "[n IN nodes(p) | {id:n.id,repo:n.repo,namespace:n.namespace,"
        "node_class:n.node_class,kind:n.kind,access_scope:n.access_scope}],"
        "[r IN relationships(p) | {id:r.id,relation_kind:r.relation_kind,"
        "from_id:startNode(r).id,to_id:endNode(r).id,scope:r.scope,"
        "evidence_anchor_ids:r.evidence_anchor_ids,evidence_class:r.evidence_class,"
        "confidence:r.confidence,provenance_ref:r.provenance_ref,"
        "temporal_ref:r.temporal_ref,trust_ref:r.trust_ref}] "
        "ORDER BY length(p),target.id,source.id,"
        "[r IN relationships(p) | r.id] SKIP $offset LIMIT $limit"
    )
    rows = graph.execute(
        query,
        {
            "projection": projection,
            "owner_slices": (
                sorted(
                    str(value)
                    for value in (owner_slice_state or {})
                    .get("owner_slices", {})
                    .values()
                )
                if owner_scoped
                else []
            ),
            "relation_slices": (
                list((owner_slice_state or {}).get("relation_slices", []))
                if owner_scoped
                else []
            ),
            "source_ids": list(dict.fromkeys(source_ids)),
            "access_scopes": scopes,
            "relation_kinds": list(dict.fromkeys(relation_kinds or [])),
            "owner": owner,
            "offset": offset,
            "limit": limit,
        },
    )
    latency = (time.perf_counter() - started) * 1000
    hits: list[dict[str, Any]] = []
    for row in rows:
        edges = list(row[11] or [])
        path_id = hashlib.sha256(
            canonical_json(
                {
                    "source_id": str(row[0]),
                    "target_id": str(row[1]),
                    "relation_ids": [str(edge.get("id") or "") for edge in edges],
                }
            ).encode("utf-8")
        ).hexdigest()
        anchors = sorted(
            {
                str(anchor)
                for edge in edges
                for anchor in (edge.get("evidence_anchor_ids") or [])
            }
        )
        hits.append(
            {
                "source_id": str(row[0]),
                "id": str(row[1]),
                "repo": str(row[2]),
                "namespace": str(row[3]),
                "node_class": str(row[4]),
                "kind": str(row[5]),
                "source_record_ids": list(row[6] or []),
                "anchor_ids": list(row[7] or []) or anchors,
                "access": {"scope": str(row[8])},
                "depth": int(row[9]),
                "evidence_path": {
                    "path_id": path_id,
                    "source_id": str(row[0]),
                    "target_id": str(row[1]),
                    "depth": int(row[9]),
                    "nodes": list(row[10] or []),
                    "relations": edges,
                    "anchor_ids": anchors,
                },
            }
        )
    return hits, latency
