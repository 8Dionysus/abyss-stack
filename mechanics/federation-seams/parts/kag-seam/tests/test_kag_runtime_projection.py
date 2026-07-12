from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[5]
PART_ROOT = REPO_ROOT / "mechanics" / "federation-seams" / "parts" / "kag-seam"
sys.path.insert(0, str(PART_ROOT))

from kag_runtime import exact, graph, vector  # noqa: E402
from kag_runtime.bundle import RetrievalBundle, canonical_json  # noqa: E402
from kag_runtime.transport import HttpJsonError  # noqa: E402


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    content = "".join(f"{canonical_json(record)}\n" for record in records).encode("utf-8")
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
    files = {key: _write_jsonl(root / f"{key}.jsonl", value) for key, value in records.items()}
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
    def request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert method == "POST"
        assert path == "/embeddings"
        return {
            "model": "fixture-embedding",
            "data": [
                {"index": index, "embedding": [3.0, 4.0, 0.0]}
                for index, _ in enumerate(payload["input"])
            ],
        }


class FakeQdrant:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, Any]] = {}
        self.aliases: dict[str, str] = {}
        self.points: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method == "GET" and path == "/collections":
            return {"result": {"collections": [{"name": key} for key in self.collections]}}
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
        if method == "PUT" and "/points?" in path:
            name = path.split("/", 3)[2]
            points = (payload or {})["points"]
            self.collections[name]["count"] += len(points)
            self.points.extend(points)
            return {"result": {"status": "completed"}}
        if method == "PUT" and path.startswith("/collections/"):
            vectors = (payload or {})["vectors"]
            self.collections[path.rsplit("/", 1)[-1]] = {
                "count": 0,
                "size": vectors["size"],
                "distance": vectors["distance"],
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
        self.counts = {"owners": 0, "nodes": 0, "relations": 0, "external_references": 0}

    def execute(self, statement: str, parameters: dict[str, Any] | None = None) -> list[list[Any]]:
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
            self.current = str(values["projection"])
        return []

    def scalar(self, statement: str, parameters: dict[str, Any]) -> Any:
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
                "SELECT id FROM documents_fts WHERE documents_fts MATCH 'evidence'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(hit[0], "aoa:fixture:retrieval-document:intro")

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

    def test_neo4j_projection_switches_current_after_complete_counts(self) -> None:
        fake = FakeGraph()
        result = graph.materialize(self.bundle, graph=fake, batch_size=1)
        self.assertEqual(result["counts"]["nodes"], 2)
        checked = graph.check(self.bundle, graph=fake)
        self.assertEqual(checked["projection_digest"], self.bundle.projection_digest)

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


if __name__ == "__main__":
    unittest.main()
