from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[5]
PART_ROOT = REPO_ROOT / "mechanics" / "federation-seams" / "parts" / "kag-seam"
sys.path.insert(0, str(PART_ROOT))

from kag_runtime import exact, graph, vector  # noqa: E402
from kag_runtime.bundle import RetrievalBundle, canonical_json  # noqa: E402
from kag_runtime.transport import HttpJsonError, JsonHttpClient  # noqa: E402
import aoa_kag_runtime_eval as runtime_eval  # noqa: E402


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    content = "".join(f"{canonical_json(record)}\n" for record in records).encode(
        "utf-8"
    )
    path.write_bytes(content)
    return {
        "path": path.name,
        "media_type": "application/x-ndjson",
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "record_count": len(records),
    }


def write_bundle(root: Path) -> RetrievalBundle:
    root.mkdir(parents=True)
    owners = [
        {
            "repo": {
                "name": "fixture",
                "namespace": "aoa:fixture",
                "owner_type": "organ",
                "root": ".",
                "git_ref": "INDEX",
            },
            "source_index_digest": _digest("source"),
            "family_digests": {"artifact": _digest("artifact")},
            "node_counts": {
                "artifact": 1,
                "anchor": 1,
                "entity": 0,
                "event": 0,
                "assertion": 0,
            },
            "relation_count": 1,
        }
    ]
    nodes = [
        {
            "id": "aoa:fixture:artifact:readme",
            "repo": "fixture",
            "namespace": "aoa:fixture",
            "node_class": "artifact",
            "kind": "markdown",
            "source_record_ids": ["source:readme"],
            "anchor_ids": ["aoa:fixture:anchor:intro"],
            "access_scope": "public",
        },
        {
            "id": "aoa:fixture:anchor:intro",
            "repo": "fixture",
            "namespace": "aoa:fixture",
            "node_class": "anchor",
            "kind": "markdown_heading",
            "source_record_ids": ["source:readme"],
            "anchor_ids": ["aoa:fixture:anchor:intro"],
            "access_scope": "public",
        },
    ]
    relations = [
        {
            "id": "aoa:fixture:relation:contains",
            "relation_kind": "contains",
            "from_id": nodes[0]["id"],
            "to_id": nodes[1]["id"],
            "source_repo": "fixture",
            "target_repo": "fixture",
            "scope": "local",
            "evidence_anchor_ids": [nodes[1]["id"]],
            "evidence_class": "deterministic",
            "confidence": 1.0,
            "temporal_ref": "temporal:current",
            "provenance_ref": "provenance:fixture",
            "trust_ref": "trust:deterministic",
        }
    ]
    external = [
        {
            "source_repo": "fixture",
            "source_anchor_id": nodes[1]["id"],
            "target_ref": "https://example.test/source",
            "reference_kind": "external-web",
        }
    ]
    text = "# Introduction\nRepo-self evidence.\n"
    documents = [
        {
            "id": "aoa:fixture:retrieval-document:intro",
            "version_id": "aoa:fixture:retrieval-document-version:intro",
            "vector_point_id": "8c8c79a5-1781-5f1c-9506-d59e04168a19",
            "repo": "fixture",
            "namespace": "aoa:fixture",
            "node_id": nodes[1]["id"],
            "node_class": "anchor",
            "kind": "markdown_heading",
            "label": "Introduction",
            "path": "README.md",
            "locator": {
                "start_line": 1,
                "end_line": 2,
                "start_column": 1,
                "end_column": 1,
                "fragment": "introduction",
                "pointer": "",
            },
            "chunk_index": 0,
            "text": text,
            "text_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "source_record_ids": ["source:readme"],
            "source_version_ids": ["source-version:readme"],
            "anchor_ids": [nodes[1]["id"]],
            "document_role": "entrypoint",
            "surface_state": "authored_source",
            "abi": {"artifact_class": "document"},
            "signs": {"digest": _digest("sign")},
            "provenance": {"extractor": "fixture"},
            "freshness": {"mode": "source_snapshot", "state": "current"},
            "access": {"scope": "public", "secrets_risk": "none"},
            "owner_return_route": {"repo": "fixture", "path": "README.md"},
            "provenance_ref": "provenance:fixture",
            "temporal_ref": "temporal:current",
            "trust_ref": "trust:deterministic",
            "profiles": {},
        }
    ]
    records = {
        "owners": owners,
        "nodes": nodes,
        "relations": relations,
        "external_references": external,
        "documents": documents,
    }
    files = {
        key: _write_jsonl(root / f"{key}.jsonl", value)
        for key, value in records.items()
    }
    manifest: dict[str, Any] = {
        "schema_version": "aoa-repo-local-kag-retrieval-bundle-v1",
        "bundle_identity": {
            "local_id": "bundle:os-abyss:repo-self-retrieval",
            "content_digest": "0" * 64,
        },
        "projection_identity": {
            "local_id": "projection:os-abyss:repo-self-retrieval",
            "content_digest": _digest("projection"),
        },
        "federation_identity": {
            "local_id": "projection:os-abyss:repo-self-federation",
            "content_digest": _digest("federation"),
        },
        "canonical_inputs": [
            {
                "repo": owners[0]["repo"],
                "source_index_digest": owners[0]["source_index_digest"],
            }
        ],
        "projection_lanes": ["exact", "lexical", "vector", "hybrid", "graph"],
        "retrieval_profile": {"chunking": "fixture"},
        "embedding_profile": {
            "id": "fixture-embedding-v1",
            "model": "fixture-embedding",
            "revision": "sha256:fixture",
            "dimensions": 3,
            "distance": "cosine",
            "normalization": "l2",
            "provider_contract": "fixture",
        },
        "summary": {
            "owner_count": 1,
            "document_count": 1,
            "text_bytes": len(text.encode("utf-8")),
        },
        "federation_summary": {
            "owner_count": 1,
            "node_count": 2,
            "relation_count": 1,
            "cross_repo_relation_count": 0,
            "external_reference_count": 1,
            "unresolved_reference_count": 0,
        },
        "files": files,
    }
    material = copy.deepcopy(manifest)
    manifest["bundle_identity"]["content_digest"] = hashlib.sha256(
        canonical_json(material).encode("utf-8")
    ).hexdigest()
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return RetrievalBundle.open(root)


class FakeEmbeddings:
    def request(
        self, method: str, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        assert method == "POST"
        assert path == "/embeddings"
        return {
            "model": "fixture-embedding",
            "data": [
                {"index": index, "embedding": [3.0, 4.0, 0.0]}
                for index, _ in enumerate(payload["input"])
            ],
        }


class AdaptiveEmbeddings(FakeEmbeddings):
    def __init__(self, max_batch_size: int) -> None:
        self.max_batch_size = max_batch_size
        self.batch_sizes: list[int] = []
        self.texts: list[str] = []

    def request(
        self, method: str, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        inputs = list(payload["input"])
        self.batch_sizes.append(len(inputs))
        if len(inputs) > self.max_batch_size:
            raise HttpJsonError(502, "transient embedding capacity")
        self.texts.extend(str(item) for item in inputs)
        return super().request(method, path, payload)


class FakeQdrant:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, Any]] = {}
        self.aliases: dict[str, str] = {}
        self.points: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method == "GET" and path == "/collections":
            return {
                "result": {"collections": [{"name": key} for key in self.collections]}
            }
        if method == "GET" and path == "/aliases":
            return {
                "result": {
                    "aliases": [
                        {"alias_name": alias, "collection_name": collection}
                        for alias, collection in self.aliases.items()
                    ]
                }
            }
        if method == "GET" and path.startswith("/collections/"):
            name = path.split("/", 3)[2]
            if name not in self.collections:
                raise HttpJsonError(404, "missing collection")
            collection = self.collections[name]
            return {
                "result": {
                    "points_count": collection["count"],
                    "payload_schema": collection.get("payload_schema", {}),
                    "config": {
                        "params": {
                            "vectors": {
                                "size": collection["size"],
                                "distance": collection["distance"],
                            }
                        }
                    },
                }
            }
        if method == "POST" and path.endswith("/points/query"):
            name = path.split("/", 3)[2]
            self.queries.append(copy.deepcopy(payload or {}))
            return {
                "result": {
                    "points": list(self.collections[name].get("points", {}).values())
                }
            }
        if method == "POST" and path.endswith("/points"):
            name = path.split("/", 3)[2]
            points = self.collections[name].get("points", {})
            return {
                "result": [
                    copy.deepcopy(points[point_id])
                    for point_id in (payload or {})["ids"]
                    if point_id in points
                ]
            }
        if method == "PUT" and "/points?" in path:
            name = path.split("/", 3)[2]
            points = (payload or {})["points"]
            stored = self.collections[name].setdefault("points", {})
            self.collections[name]["count"] += sum(
                point["id"] not in stored for point in points
            )
            stored.update({point["id"]: copy.deepcopy(point) for point in points})
            self.points.extend(points)
            return {"result": {"status": "completed"}}
        if method == "PUT" and "/index?" in path:
            name = path.split("/", 3)[2]
            schema = self.collections[name].setdefault("payload_schema", {})
            values = payload or {}
            schema[values["field_name"]] = {"data_type": values["field_schema"]}
            return {"result": {"status": "completed"}}
        if method == "PUT" and path.startswith("/collections/"):
            vectors = (payload or {})["vectors"]
            self.collections[path.rsplit("/", 1)[-1]] = {
                "count": 0,
                "size": vectors["size"],
                "distance": vectors["distance"],
                "payload_schema": {},
                "points": {},
            }
            return {"result": True}
        if method == "DELETE" and path.startswith("/collections/"):
            self.collections.pop(path.rsplit("/", 1)[-1], None)
            return {"result": True}
        if method == "POST" and path == "/collections/aliases":
            for action in (payload or {})["actions"]:
                if "delete_alias" in action:
                    self.aliases.pop(action["delete_alias"]["alias_name"], None)
                else:
                    value = action["create_alias"]
                    self.aliases[value["alias_name"]] = value["collection_name"]
            return {"result": True}
        raise AssertionError((method, path, payload))


class FakeGraph:
    database = "neo4j"

    def __init__(self) -> None:
        self.current: str | None = None
        self.previous: str | None = None
        self.counts = {
            "owners": 0,
            "nodes": 0,
            "relations": 0,
            "external_references": 0,
        }
        self.stale_nodes = 0
        self.cleanup_limits: list[int] = []

    def execute(
        self, statement: str, parameters: dict[str, Any] | None = None
    ) -> list[list[Any]]:
        values = parameters or {}
        rows = values.get("rows", [])
        if "UNWIND" in statement and "AOA_KAG_EXTERNAL_REFERENCE" in statement:
            self.counts["external_references"] += len(rows)
        elif "UNWIND" in statement and "AOA_KAG_RELATION" in statement:
            self.counts["relations"] += len(rows)
        elif "UNWIND" in statement and "MERGE (o:AoAKagOwner" in statement:
            self.counts["owners"] += len(rows)
        elif "UNWIND" in statement and "MERGE (n:AoAKagNode" in statement:
            self.counts["nodes"] += len(rows)
        if "repo-self-current" in statement and "SET p.previous_digest" in statement:
            self.previous = self.current
            self.current = str(values["projection"])
        return []

    def scalar(self, statement: str, parameters: dict[str, Any]) -> Any:
        if "DETACH DELETE n" in statement:
            limit = int(parameters["limit"])
            self.cleanup_limits.append(limit)
            removed = min(self.stale_nodes, limit)
            self.stale_nodes -= removed
            return removed
        if "p.previous_digest" in statement:
            return self.previous
        if "p.current_digest" in statement:
            return self.current
        if "AoAKagOwner" in statement:
            return self.counts["owners"]
        if "AoAKagNode" in statement:
            return self.counts["nodes"]
        if "AOA_KAG_EXTERNAL_REFERENCE" in statement:
            return self.counts["external_references"]
        if "AOA_KAG_RELATION" in statement:
            return self.counts["relations"]
        raise AssertionError(statement)


class KagRuntimeProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = write_bundle(self.root / "bundle")

    def test_bundle_verification_detects_drift(self) -> None:
        report = self.bundle.verify()
        self.assertEqual(report["files"]["documents"]["record_count"], 1)
        with self.bundle.path("documents").open("a", encoding="utf-8") as handle:
            handle.write("{}\n")
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            self.bundle.verify()

    def test_sqlite_projection_supports_exact_and_fts_reads(self) -> None:
        destination = self.root / "runtime" / "repo-self.sqlite3"
        result = exact.materialize(self.bundle, destination)
        self.assertEqual(result["counts"]["documents"], 1)
        checked = exact.check(self.bundle, destination)
        self.assertEqual(checked["counts"]["relations"], 1)
        connection = sqlite3.connect(destination)
        try:
            hit = connection.execute(
                "SELECT id FROM documents_fts WHERE documents_fts MATCH "
                "'repo:fixture AND kind:markdown_heading AND evidence'"
            ).fetchone()
            filter_columns = [
                row[2]
                for row in connection.execute("PRAGMA index_info(documents_filter)")
            ]
        finally:
            connection.close()
        self.assertEqual(hit[0], "aoa:fixture:retrieval-document:intro")
        self.assertEqual(
            filter_columns,
            ["repo", "path", "node_class", "kind", "start_line", "chunk_index", "id"],
        )

    def test_qdrant_projection_uses_bundle_point_identity_and_alias(self) -> None:
        qdrant = FakeQdrant()
        result = vector.materialize(
            self.bundle,
            qdrant=qdrant,
            embeddings=FakeEmbeddings(),
            batch_size=1,
        )
        self.assertEqual(result["point_count"], 1)
        self.assertEqual(
            qdrant.points[0]["id"],
            "8c8c79a5-1781-5f1c-9506-d59e04168a19",
        )
        self.assertEqual(qdrant.points[0]["vector"], [0.6, 0.8, 0.0])
        checked = vector.check(self.bundle, qdrant=qdrant)
        self.assertEqual(checked["collection"], result["collection"])

    def test_qdrant_query_uses_active_collection_and_owner_filter(self) -> None:
        qdrant = FakeQdrant()
        collection = "aoa_kag_repo_self_fixture"
        qdrant.collections[collection] = {
            "count": 1,
            "size": 3,
            "distance": "Cosine",
            "points": {
                "fixture": {
                    "id": "fixture",
                    "payload": {"id": "fixture", "repo": "fixture"},
                }
            },
        }
        qdrant.aliases[vector.DEFAULT_ALIAS] = collection
        hits, latency = vector.search(
            "repository evidence",
            qdrant=qdrant,
            embeddings=FakeEmbeddings(),
            profile=dict(self.bundle.manifest["embedding_profile"]),
            repo="fixture",
        )
        self.assertEqual(hits[0]["id"], "fixture")
        self.assertGreaterEqual(latency, 0.0)
        self.assertEqual(
            qdrant.queries[0]["filter"]["must"],
            [{"key": "repo", "match": {"value": "fixture"}}],
        )

    def test_embedding_batches_retry_then_split_on_transient_capacity(self) -> None:
        client = AdaptiveEmbeddings(max_batch_size=2)
        documents = [{"text": f"document {index}"} for index in range(4)]
        with mock.patch.object(vector.time, "sleep"):
            vectors = vector._embedding_vectors_resilient(
                client,
                documents,
                dict(self.bundle.manifest["embedding_profile"]),
            )

        self.assertEqual(len(vectors), 4)
        self.assertEqual(client.batch_sizes[-2:], [2, 2])
        self.assertEqual(client.texts, [item["text"] for item in documents])

    def test_qdrant_projection_resumes_confirmed_document_prefix(self) -> None:
        source = next(self.bundle.records("documents"))
        documents = []
        for index in range(4):
            document = copy.deepcopy(source)
            document["id"] = f"aoa:fixture:retrieval-document:{index}"
            document["version_id"] = f"aoa:fixture:retrieval-document-version:{index}"
            document["vector_point_id"] = f"00000000-0000-5000-8000-{index:012d}"
            document["text"] = f"document {index}"
            document["text_digest"] = hashlib.sha256(
                document["text"].encode("utf-8")
            ).hexdigest()
            documents.append(document)

        class BundleView:
            projection_digest = self.bundle.projection_digest
            manifest = copy.deepcopy(self.bundle.manifest)

            def records(self, key: str):
                assert key == "documents"
                yield from documents

        bundle = BundleView()
        bundle.manifest["files"]["documents"]["record_count"] = len(documents)
        collection = f"{vector.COLLECTION_PREFIX}{bundle.projection_digest[:20]}"
        qdrant = FakeQdrant()
        qdrant.collections[collection] = {
            "count": 2,
            "size": 3,
            "distance": "Cosine",
            "payload_schema": {},
            "points": {},
        }
        embeddings = AdaptiveEmbeddings(max_batch_size=2)

        result = vector.materialize(
            bundle,
            qdrant=qdrant,
            embeddings=embeddings,
            batch_size=2,
        )

        self.assertEqual(result["point_count"], 4)
        self.assertEqual(result["resumed_from_point_count"], 2)
        self.assertEqual(embeddings.texts, ["document 2", "document 3"])
        self.assertEqual(
            [point["id"] for point in qdrant.points],
            [
                documents[2]["vector_point_id"],
                documents[3]["vector_point_id"],
            ],
        )

    def test_qdrant_projection_reuses_unchanged_vectors_from_previous_alias(
        self,
    ) -> None:
        source = next(self.bundle.records("documents"))
        unchanged = copy.deepcopy(source)
        changed = copy.deepcopy(source)
        changed["id"] = "aoa:fixture:retrieval-document:changed"
        changed["version_id"] = "aoa:fixture:retrieval-document-version:changed"
        changed["vector_point_id"] = "00000000-0000-5000-8000-000000000002"
        changed["text"] = "changed document"
        changed["text_digest"] = hashlib.sha256(changed["text"].encode()).hexdigest()

        class BundleView:
            projection_digest = "b" * 64
            manifest = copy.deepcopy(self.bundle.manifest)

            def records(self, key: str):
                assert key == "documents"
                yield unchanged
                yield changed

        bundle = BundleView()
        bundle.manifest["files"]["documents"]["record_count"] = 2
        previous = "aoa_kag_repo_self_previous"
        qdrant = FakeQdrant()
        qdrant.collections[previous] = {
            "count": 2,
            "size": 3,
            "distance": "Cosine",
            "payload_schema": {},
            "points": {
                unchanged["vector_point_id"]: {
                    "id": unchanged["vector_point_id"],
                    "vector": [0.6, 0.8, 0.0],
                    "payload": {
                        "text_digest": unchanged["text_digest"],
                        "embedding_profile_id": "fixture-embedding-v1",
                    },
                },
                changed["vector_point_id"]: {
                    "id": changed["vector_point_id"],
                    "vector": [0.0, 0.0, 1.0],
                    "payload": {
                        "text_digest": "stale",
                        "embedding_profile_id": "fixture-embedding-v1",
                    },
                },
            },
        }
        qdrant.aliases[vector.DEFAULT_ALIAS] = previous
        embeddings = AdaptiveEmbeddings(max_batch_size=2)

        result = vector.materialize(
            bundle,
            qdrant=qdrant,
            embeddings=embeddings,
            batch_size=2,
        )

        self.assertEqual(result["reused_point_count"], 1)
        self.assertEqual(result["embedded_point_count"], 1)
        self.assertEqual(embeddings.texts, ["changed document"])
        self.assertEqual(qdrant.points[0]["vector"], [0.6, 0.8, 0.0])
        self.assertEqual(qdrant.points[1]["vector"], [0.6, 0.8, 0.0])

    def test_qdrant_projection_bounds_dense_changed_embedding_batches(self) -> None:
        source = next(self.bundle.records("documents"))
        documents = []
        previous_points = {}
        for index in range(6):
            document = copy.deepcopy(source)
            document["id"] = f"aoa:fixture:retrieval-document:{index}"
            document["version_id"] = f"aoa:fixture:retrieval-document-version:{index}"
            document["vector_point_id"] = f"00000000-0000-5000-8000-{index:012d}"
            document["text"] = f"changed document {index}"
            document["text_digest"] = hashlib.sha256(
                document["text"].encode()
            ).hexdigest()
            documents.append(document)
            previous_points[document["vector_point_id"]] = {
                "id": document["vector_point_id"],
                "vector": [0.0, 0.0, 1.0],
                "payload": {
                    "text_digest": "stale",
                    "embedding_profile_id": "fixture-embedding-v1",
                },
            }

        class BundleView:
            projection_digest = "c" * 64
            manifest = copy.deepcopy(self.bundle.manifest)

            def records(self, key: str):
                assert key == "documents"
                yield from documents

        bundle = BundleView()
        bundle.manifest["files"]["documents"]["record_count"] = len(documents)
        previous = "aoa_kag_repo_self_previous"
        qdrant = FakeQdrant()
        qdrant.collections[previous] = {
            "count": len(documents),
            "size": 3,
            "distance": "Cosine",
            "payload_schema": {},
            "points": previous_points,
        }
        qdrant.aliases[vector.DEFAULT_ALIAS] = previous
        embeddings = AdaptiveEmbeddings(max_batch_size=2)

        result = vector.materialize(
            bundle,
            qdrant=qdrant,
            embeddings=embeddings,
            batch_size=2,
        )

        self.assertEqual(result["embedded_point_count"], len(documents))
        self.assertEqual(embeddings.batch_sizes, [2, 2, 2])
        self.assertEqual(
            embeddings.texts,
            [document["text"] for document in documents],
        )

    def test_neo4j_projection_switches_current_after_complete_counts(self) -> None:
        fake = FakeGraph()
        result = graph.materialize(self.bundle, graph=fake, batch_size=1)
        self.assertEqual(result["counts"]["nodes"], 2)
        checked = graph.check(self.bundle, graph=fake)
        self.assertEqual(checked["projection_digest"], self.bundle.projection_digest)

    def test_neo4j_multihop_query_returns_grounded_chain(self) -> None:
        projection = mock.Mock(spec=graph.Neo4jProjection)
        projection.execute.return_value = [
            [
                "target",
                "fixture",
                ["source:target"],
                ["anchor:target"],
                "public",
                "relation:first",
                ["anchor:first"],
                "provenance:first",
                "trust:first",
                "relation:second",
                ["anchor:second"],
                "provenance:second",
                "trust:second",
            ]
        ]
        hits, latency, completeness = graph.search_multihop(
            graph=projection,
            projection="projection",
            source_id="source",
            first_relation="defines",
            second_relation="calls",
            source_path="README.md",
        )
        self.assertEqual(hits[0]["id"], "target")
        self.assertGreaterEqual(latency, 0.0)
        self.assertEqual(completeness, 1.0)

    def test_neo4j_projection_resumes_bounded_retention_after_cutover(self) -> None:
        fake = FakeGraph()
        fake.current = self.bundle.projection_digest
        fake.previous = "previous-projection"
        fake.counts = {
            "owners": 1,
            "nodes": 2,
            "relations": 1,
            "external_references": 1,
        }
        fake.stale_nodes = 2500

        result = graph.materialize(self.bundle, graph=fake, batch_size=1000)

        self.assertEqual(result["previous_projection_digest"], "previous-projection")
        self.assertEqual(
            result["retained_projection_digests"],
            [self.bundle.projection_digest, "previous-projection"],
        )
        self.assertEqual(fake.stale_nodes, 0)
        self.assertTrue(fake.cleanup_limits)
        self.assertTrue(all(limit == 1000 for limit in fake.cleanup_limits))

    def test_http_client_wraps_remote_disconnect(self) -> None:
        client = JsonHttpClient("http://example.test")
        with mock.patch(
            "kag_runtime.transport.request.urlopen",
            side_effect=RemoteDisconnected("closed"),
        ):
            with self.assertRaises(HttpJsonError) as captured:
                client.request("GET", "/health")
        self.assertEqual(captured.exception.status, 0)

    def test_root_command_writes_exact_receipt_and_checks_projection(self) -> None:
        stack_root = self.root / "stack"
        command = REPO_ROOT / "scripts" / "aoa-kag-runtime-projection"
        args = [
            sys.executable,
            str(command),
            "--bundle-dir",
            str(self.bundle.root),
            "--stack-root",
            str(stack_root),
            "--target",
            "exact",
        ]
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        current = stack_root / "Knowledge" / "kag" / "repo-self" / "current.json"
        self.assertTrue(current.is_file())
        checked = subprocess.run(
            [*args, "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, msg=checked.stderr)

    def test_retrieval_eval_config_has_unique_semantic_cases(self) -> None:
        config = runtime_eval.load_config(runtime_eval.DEFAULT_CASES_PATH)
        names = [case["name"] for case in config["semantic_cases"]]
        self.assertEqual(config["expected_owner_count"], 24)
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("graph_recall_advantage", config["thresholds"]["minimums"])

    def test_retrieval_eval_exact_lexical_and_quality_metrics(self) -> None:
        sqlite_path = self.root / "repo-self.sqlite3"
        exact.materialize(self.bundle, sqlite_path)
        connection = sqlite3.connect(
            f"file:{sqlite_path}?mode=ro&immutable=1",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        try:
            target = runtime_eval.exact_targets(connection)[0]
            exact_hits, _ = runtime_eval.exact_search(connection, target["id"])
            lexical_hits, _ = runtime_eval.lexical_search(
                connection,
                target["label"],
                repo=target["repo"],
                kind=target["kind"],
            )
            quality = runtime_eval.canonical_quality(connection)
        finally:
            connection.close()
        self.assertEqual(runtime_eval.hit_id(exact_hits[0]), target["id"])
        self.assertEqual(runtime_eval.hit_id(lexical_hits[0]), target["id"])
        self.assertEqual(quality["relation_endpoint_resolution"], 1.0)
        self.assertEqual(quality["unsupported_edge_rate"], 0.0)

    def test_retrieval_eval_weighted_fusion_keeps_lexical_weight(self) -> None:
        lexical = [
            {"id": "lexical-first", "payload": {"id": "lexical-first"}},
            {"id": "shared", "payload": {"id": "shared"}},
        ]
        vector_hits = [
            {"id": "shared", "payload": {"id": "shared"}},
            {"id": "vector-second", "payload": {"id": "vector-second"}},
        ]
        fused = runtime_eval.reciprocal_rank_fusion(lexical, vector_hits)
        self.assertEqual(
            [runtime_eval.hit_id(hit) for hit in fused[:2]],
            ["lexical-first", "shared"],
        )


if __name__ == "__main__":
    unittest.main()
