from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any, Callable
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[5]
PART_ROOT = REPO_ROOT / "mechanics" / "federation-seams" / "parts" / "kag-seam"
sys.path.insert(0, str(PART_ROOT))

from kag_runtime import exact, graph, vector  # noqa: E402
from kag_runtime.application import KagApplication, RuntimeConfig  # noqa: E402
from kag_runtime.bundle import (  # noqa: E402
    RetrievalBundle,
    canonical_json,
    write_json_atomic,
)
from kag_runtime.transport import HttpJsonError, JsonHttpClient  # noqa: E402
import aoa_kag_runtime_eval as runtime_eval  # noqa: E402
import aoa_kag_runtime_projection as runtime_projection  # noqa: E402


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
            "family_digests": {
                kind: _digest(kind)
                for kind in (
                    "anchor",
                    "artifact",
                    "assertion",
                    "entity",
                    "event",
                    "relation",
                )
            },
            "node_counts": {
                "artifact": 1,
                "anchor": 1,
                "entity": 1,
                "event": 1,
                "assertion": 1,
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
            "record_form": "projection_handle",
            "label": "README.md",
            "path": "README.md",
            "search_text": "README.md markdown repository introduction",
            "source_record_ids": ["source:readme"],
            "anchor_ids": ["aoa:fixture:anchor:intro"],
            "access_scope": "public",
            "document_role": "readme",
            "surface_state": "authored_source",
            "provenance_ref": "provenance:fixture",
            "temporal_ref": "temporal:current",
            "trust_ref": "trust:deterministic",
        },
        {
            "id": "aoa:fixture:anchor:intro",
            "repo": "fixture",
            "namespace": "aoa:fixture",
            "node_class": "anchor",
            "kind": "markdown_heading",
            "record_form": "projection_handle",
            "label": "Introduction",
            "path": "README.md",
            "search_text": "Introduction repository evidence README.md markdown heading",
            "source_record_ids": ["source:readme"],
            "anchor_ids": ["aoa:fixture:anchor:intro"],
            "access_scope": "public",
            "document_role": "readme",
            "surface_state": "authored_source",
            "provenance_ref": "provenance:fixture",
            "temporal_ref": "temporal:current",
            "trust_ref": "trust:deterministic",
        },
        {
            "id": "aoa:fixture:entity:repository",
            "repo": "fixture",
            "namespace": "aoa:fixture",
            "node_class": "entity",
            "kind": "repository",
            "record_form": "projection_handle",
            "label": "Fixture repository",
            "path": "README.md",
            "search_text": "Fixture repository entity owner route",
            "source_record_ids": ["source:readme"],
            "anchor_ids": ["aoa:fixture:anchor:intro"],
            "access_scope": "public",
            "document_role": "readme",
            "surface_state": "authored_source",
            "provenance_ref": "provenance:fixture",
            "temporal_ref": "temporal:current",
            "trust_ref": "trust:deterministic",
        },
        {
            "id": "aoa:fixture:event:release",
            "repo": "fixture",
            "namespace": "aoa:fixture",
            "node_class": "event",
            "kind": "release",
            "record_form": "projection_handle",
            "label": "Fixture release",
            "path": "",
            "search_text": "Fixture release event observed history",
            "source_record_ids": [],
            "anchor_ids": [],
            "access_scope": "public",
            "document_role": "repository_event",
            "surface_state": "observed_history",
            "provenance_ref": "provenance:fixture",
            "temporal_ref": "temporal:current",
            "trust_ref": "trust:deterministic",
        },
        {
            "id": "aoa:fixture:assertion:owner",
            "repo": "fixture",
            "namespace": "aoa:fixture",
            "node_class": "assertion",
            "kind": "ownership",
            "record_form": "projection_handle",
            "label": "owned_by: fixture",
            "path": "README.md",
            "search_text": "owned by fixture assertion repository",
            "source_record_ids": ["source:readme"],
            "anchor_ids": ["aoa:fixture:anchor:intro"],
            "access_scope": "public",
            "document_role": "readme",
            "surface_state": "authored_source",
            "provenance_ref": "provenance:fixture",
            "temporal_ref": "temporal:current",
            "trust_ref": "trust:deterministic",
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
            "record_form": "canonical_record",
            "label": "contains: README.md -> Introduction",
            "path": "README.md",
            "search_text": "contains README.md Introduction relation",
            "source_record_ids": ["source:readme"],
            "access_scope": "public",
            "document_role": "readme",
            "surface_state": "authored_source",
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
                "family_digests": owners[0]["family_digests"],
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
            "node_count": 5,
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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _replace_fixture(value: Any, replacement: str) -> Any:
    if isinstance(value, str):
        return value.replace("fixture", replacement).replace(
            "Fixture", replacement.title()
        )
    if isinstance(value, list):
        return [_replace_fixture(item, replacement) for item in value]
    if isinstance(value, dict):
        return {key: _replace_fixture(item, replacement) for key, item in value.items()}
    return value


def _finalize_bundle(
    root: Path,
    manifest: dict[str, Any],
    records: dict[str, list[dict[str, Any]]],
) -> RetrievalBundle:
    manifest["files"] = {
        key: _write_jsonl(root / f"{key}.jsonl", value)
        for key, value in records.items()
    }
    manifest["summary"]["owner_count"] = len(records["owners"])
    manifest["summary"]["document_count"] = len(records["documents"])
    manifest["summary"]["text_bytes"] = sum(
        len(str(item["text"]).encode("utf-8")) for item in records["documents"]
    )
    manifest["federation_summary"].update(
        {
            "owner_count": len(records["owners"]),
            "node_count": len(records["nodes"]),
            "relation_count": len(records["relations"]),
            "external_reference_count": len(records["external_references"]),
        }
    )
    manifest["bundle_identity"]["content_digest"] = "0" * 64
    manifest["bundle_identity"]["content_digest"] = hashlib.sha256(
        canonical_json(manifest).encode("utf-8")
    ).hexdigest()
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return RetrievalBundle.open(root)


def write_two_owner_bundle(root: Path) -> RetrievalBundle:
    bundle = write_bundle(root)
    manifest = copy.deepcopy(bundle.manifest)
    records = {
        key: _read_jsonl(bundle.path(key))
        for key in ("owners", "nodes", "relations", "external_references", "documents")
    }
    for key in records:
        records[key].extend(_replace_fixture(copy.deepcopy(records[key]), "fixture-b"))
    second_owner = records["owners"][1]
    second_owner["source_index_digest"] = _digest("source-b")
    second_owner["repo"]["git_ref"] = "INDEX-B"
    records["documents"][1]["vector_point_id"] = "00000000-0000-0000-0000-000000000002"
    manifest["canonical_inputs"] = [
        {
            "repo": copy.deepcopy(item["repo"]),
            "source_index_digest": item["source_index_digest"],
            "family_digests": copy.deepcopy(item["family_digests"]),
        }
        for item in records["owners"]
    ]
    manifest["projection_identity"]["content_digest"] = _digest("projection-two")
    manifest["federation_identity"]["content_digest"] = _digest("federation-two")
    return _finalize_bundle(root, manifest, records)


def write_changed_owner_bundle(
    source: RetrievalBundle,
    root: Path,
    *,
    owner: str,
    marker: str,
) -> RetrievalBundle:
    shutil.copytree(source.root, root)
    manifest = copy.deepcopy(source.manifest)
    records = {
        key: _read_jsonl(root / f"{key}.jsonl")
        for key in ("owners", "nodes", "relations", "external_references", "documents")
    }
    for item in records["owners"]:
        if item["repo"]["name"] == owner:
            item["source_index_digest"] = _digest(f"{owner}:{marker}")
    for item in records["nodes"]:
        if item["repo"] == owner:
            item["search_text"] = f"{item['search_text']} {marker}"
    for item in records["relations"]:
        if owner in {item["source_repo"], item["target_repo"]}:
            item["search_text"] = f"{item['search_text']} {marker}"
    for item in records["external_references"]:
        if owner in {item["source_repo"], item.get("target_repo")}:
            item["target_ref"] = f"{item['target_ref']}?version={marker}"
    for item in records["documents"]:
        if item["repo"] == owner:
            item["text"] = f"# Changed owner\n{marker}\n"
            item["text_digest"] = hashlib.sha256(
                item["text"].encode("utf-8")
            ).hexdigest()
            item["version_id"] = f"{item['version_id']}:{marker}"
    for item in manifest["canonical_inputs"]:
        if item["repo"]["name"] == owner:
            item["source_index_digest"] = _digest(f"{owner}:{marker}")
            if "corpus_identity" in item:
                item["corpus_identity"]["content_digest"] = "sha256:" + _digest(
                    f"corpus:{owner}:{marker}"
                )
                item["distribution_identity"]["content_digest"] = "sha256:" + _digest(
                    f"distribution:{owner}:{marker}"
                )
    manifest["projection_identity"]["content_digest"] = _digest(
        f"projection:{owner}:{marker}"
    )
    manifest["federation_identity"]["content_digest"] = _digest(
        f"federation:{owner}:{marker}"
    )
    return _finalize_bundle(root, manifest, records)


def write_mutated_bundle(
    source: RetrievalBundle,
    root: Path,
    mutate: Callable[[dict[str, Any], dict[str, list[dict[str, Any]]]], None],
) -> RetrievalBundle:
    shutil.copytree(source.root, root)
    manifest = copy.deepcopy(source.manifest)
    records = {
        key: _read_jsonl(root / f"{key}.jsonl")
        for key in (
            "owners",
            "nodes",
            "relations",
            "external_references",
            "documents",
        )
    }
    mutate(manifest, records)
    return _finalize_bundle(root, manifest, records)


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
        self.retained_digests: list[str] = []
        self.cleanup_keep: list[str] = []
        self.observed_channels: list[str] = []
        self.counts = {
            "owners": 0,
            "nodes": 0,
            "relations": 0,
            "external_references": 0,
        }
        self.stale_nodes = 0
        self.cleanup_limits: list[int] = []
        self.slice_owners: set[tuple[str, str]] = set()
        self.slice_nodes: set[tuple[str, str]] = set()
        self.slice_relations: set[tuple[str, str]] = set()
        self.slice_external: set[tuple[str, str]] = set()

    def execute(
        self, statement: str, parameters: dict[str, Any] | None = None
    ) -> list[list[Any]]:
        values = parameters or {}
        rows = values.get("rows", [])
        if "UNWIND" in statement and "AOA_KAG_EXTERNAL_REFERENCE_SLICE" in statement:
            self.slice_external.update(
                (str(row["slice_digest"]), str(row["id"])) for row in rows
            )
        elif "UNWIND" in statement and "AOA_KAG_RELATION_SLICE" in statement:
            self.slice_relations.update(
                (str(row["slice_digest"]), str(row["id"])) for row in rows
            )
        elif "UNWIND" in statement and "MERGE (o:AoAKagOwnerSlice" in statement:
            self.slice_owners.update(
                (str(row["slice_digest"]), str(row["repo"])) for row in rows
            )
        elif "UNWIND" in statement and "MERGE (n:AoAKagNodeSlice" in statement:
            self.slice_nodes.update(
                (str(row["slice_digest"]), str(row["id"])) for row in rows
            )
        elif "UNWIND" in statement and "AOA_KAG_EXTERNAL_REFERENCE" in statement:
            self.counts["external_references"] += len(rows)
        elif "UNWIND" in statement and "AOA_KAG_RELATION" in statement:
            self.counts["relations"] += len(rows)
        elif "UNWIND" in statement and "MERGE (o:AoAKagOwner" in statement:
            self.counts["owners"] += len(rows)
        elif "UNWIND" in statement and "MERGE (n:AoAKagNode" in statement:
            self.counts["nodes"] += len(rows)
        if "SET p.previous_digest" in statement:
            self.observed_channels.append(str(values.get("channel") or ""))
            self.previous = self.current
            self.current = str(values["projection"])
        return []

    def scalar(self, statement: str, parameters: dict[str, Any]) -> Any:
        if "DETACH DELETE n" in statement:
            limit = int(parameters["limit"])
            self.cleanup_limits.append(limit)
            self.cleanup_keep = list(parameters["keep"])
            removed = min(self.stale_nodes, limit)
            self.stale_nodes -= removed
            return removed
        if "RETURN collect(digest)" in statement:
            return list(
                dict.fromkeys(
                    item
                    for item in (
                        self.current,
                        self.previous,
                        *self.retained_digests,
                    )
                    if item
                )
            )
        if "p.previous_digest" in statement:
            self.observed_channels.append(str(parameters.get("channel") or ""))
            return self.previous
        if "p.current_digest" in statement:
            self.observed_channels.append(str(parameters.get("channel") or ""))
            return self.current
        slices = set(parameters.get("slices", []))
        if "AoAKagOwnerSlice" in statement:
            return sum(slice_digest in slices for slice_digest, _ in self.slice_owners)
        if "AoAKagNodeSlice" in statement:
            return sum(slice_digest in slices for slice_digest, _ in self.slice_nodes)
        if "AOA_KAG_EXTERNAL_REFERENCE_SLICE" in statement:
            return sum(
                slice_digest in slices for slice_digest, _ in self.slice_external
            )
        if "AOA_KAG_RELATION_SLICE" in statement:
            return sum(
                slice_digest in slices for slice_digest, _ in self.slice_relations
            )
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
        document_path = self.bundle.path("documents")
        original = document_path.read_text(encoding="utf-8")
        with document_path.open("a", encoding="utf-8") as handle:
            handle.write(original)
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            self.bundle.verify()

    def test_bundle_verification_accepts_paired_legacy_tiered_identities(
        self,
    ) -> None:
        def add_tiered_identities(
            manifest: dict[str, Any],
            _records: dict[str, list[dict[str, Any]]],
        ) -> None:
            canonical_input = manifest["canonical_inputs"][0]
            canonical_input["corpus_identity"] = {
                "content_digest": "sha256:" + _digest("corpus")
            }
            canonical_input["distribution_identity"] = {
                "content_digest": "sha256:" + _digest("distribution"),
                "delivery_state": "complete",
                "complete": True,
                "manifest_schema": ("aoa-repo-local-kag-distribution-manifest-v1"),
                "routes": {"local_cas": 1},
            }

        legacy = write_mutated_bundle(
            self.bundle,
            self.root / "legacy-tiered-bundle",
            add_tiered_identities,
        )
        self.assertEqual(legacy.verify()["owners"], ["fixture"])

    def test_bundle_verification_rejects_unpaired_tiered_identity(self) -> None:
        def add_only_corpus(
            manifest: dict[str, Any],
            _records: dict[str, list[dict[str, Any]]],
        ) -> None:
            manifest["canonical_inputs"][0]["corpus_identity"] = {
                "content_digest": "sha256:" + _digest("corpus")
            }

        broken = write_mutated_bundle(
            self.bundle,
            self.root / "unpaired-tiered-bundle",
            add_only_corpus,
        )
        with self.assertRaisesRegex(RuntimeError, "tiered identities must be paired"):
            broken.verify()

    def test_bundle_verification_rejects_canonical_owner_disagreement(self) -> None:
        def change_only_canonical_input(
            manifest: dict[str, Any],
            _records: dict[str, list[dict[str, Any]]],
        ) -> None:
            manifest["canonical_inputs"][0]["source_index_digest"] = _digest(
                "unbound-source"
            )

        broken = write_mutated_bundle(
            self.bundle,
            self.root / "unbound-canonical-input",
            change_only_canonical_input,
        )
        with self.assertRaisesRegex(RuntimeError, "disagrees with its owner record"):
            broken.verify()

    def test_bundle_verification_rejects_incomplete_family_identity(self) -> None:
        def remove_family(
            manifest: dict[str, Any],
            records: dict[str, list[dict[str, Any]]],
        ) -> None:
            manifest["canonical_inputs"][0]["family_digests"].pop("relation")
            records["owners"][0]["family_digests"].pop("relation")

        broken = write_mutated_bundle(
            self.bundle,
            self.root / "incomplete-family-identity",
            remove_family,
        )
        with self.assertRaisesRegex(RuntimeError, "family digests are invalid"):
            broken.verify()

    def test_sqlite_projection_supports_exact_and_fts_reads(self) -> None:
        destination = self.root / "runtime" / "repo-self.sqlite3"
        result = exact.materialize(self.bundle, destination)
        self.assertEqual(result["counts"]["documents"], 1)
        checked = exact.check(self.bundle, destination)
        self.assertEqual(checked["counts"]["relations"], 1)
        connection = sqlite3.connect(destination)
        try:
            hit = connection.execute(
                "SELECT d.id FROM documents_fts "
                "JOIN documents d ON d.rowid=documents_fts.rowid "
                "WHERE documents_fts MATCH "
                "'repo:fixture AND kind:markdown AND kind:heading AND evidence'"
            ).fetchone()
            filter_columns = [
                row[2]
                for row in connection.execute("PRAGMA index_info(documents_path)")
            ]
            objects = dict(
                connection.execute(
                    "SELECT name,type FROM sqlite_master "
                    "WHERE name IN ('nodes','records_fts_content','documents_fts_content')"
                )
            )
        finally:
            connection.close()
        self.assertEqual(hit[0], "aoa:fixture:retrieval-document:intro")
        self.assertEqual(
            filter_columns,
            ["path", "repo", "node_class", "kind", "start_line", "chunk_index", "id"],
        )
        self.assertEqual(objects, {"nodes": "view"})

    def test_sqlite_owner_incremental_update_reuses_unaffected_owner_slice(
        self,
    ) -> None:
        first = write_two_owner_bundle(self.root / "two-owner")
        second = write_changed_owner_bundle(
            first,
            self.root / "two-owner-next",
            owner="fixture",
            marker="changed-owner-marker",
        )
        destination = self.root / "runtime" / "repo-self.sqlite3"
        exact.materialize(first, destination)
        before = sqlite3.connect(destination)
        try:
            unaffected_before = before.execute(
                "SELECT payload_json FROM records WHERE repo='fixture-b' ORDER BY id"
            ).fetchall()
        finally:
            before.close()

        result = exact.materialize_affected_owners(
            second,
            destination,
            affected_owners=["fixture"],
        )
        exact.check(second, destination)

        after = sqlite3.connect(destination)
        try:
            unaffected_after = after.execute(
                "SELECT payload_json FROM records WHERE repo='fixture-b' ORDER BY id"
            ).fetchall()
            changed_document = after.execute(
                "SELECT d.id FROM documents_fts "
                "JOIN documents d ON d.rowid=documents_fts.rowid "
                "WHERE documents_fts MATCH 'changed AND owner AND marker'"
            ).fetchone()
            old_document = after.execute(
                "SELECT d.id FROM documents_fts "
                "JOIN documents d ON d.rowid=documents_fts.rowid "
                "WHERE documents_fts MATCH 'evidence' AND d.repo='fixture'"
            ).fetchone()
        finally:
            after.close()

        self.assertEqual(result["update_mode"], "owner_incremental")
        self.assertEqual(result["affected_owners"], ["fixture"])
        self.assertEqual(result["changed_canonical_inputs"], ["fixture"])
        self.assertEqual(unaffected_before, unaffected_after)
        self.assertEqual(
            changed_document[0],
            "aoa:fixture:retrieval-document:intro",
        )
        self.assertIsNone(old_document)
        self.assertEqual(result["rows_inserted"]["owners"], 1)

    def test_sqlite_owner_incremental_update_rejects_omitted_changed_owner(
        self,
    ) -> None:
        first = write_two_owner_bundle(self.root / "two-owner")
        second = write_changed_owner_bundle(
            first,
            self.root / "two-owner-next",
            owner="fixture",
            marker="changed-owner-marker",
        )
        destination = self.root / "runtime" / "repo-self.sqlite3"
        exact.materialize(first, destination)

        with self.assertRaisesRegex(
            RuntimeError,
            "omits changed canonical inputs",
        ):
            exact.materialize_affected_owners(
                second,
                destination,
                affected_owners=["fixture-b"],
            )

    def test_sqlite_owner_incremental_update_preserves_and_rolls_back_last_good(
        self,
    ) -> None:
        first = write_two_owner_bundle(self.root / "rollback-two-owner")
        second = write_changed_owner_bundle(
            first,
            self.root / "rollback-two-owner-next",
            owner="fixture",
            marker="rollback-owner-marker",
        )
        destination = self.root / "runtime" / "repo-self.sqlite3"
        exact.materialize(first, destination)
        advanced = exact.materialize_affected_owners(
            second,
            destination,
            affected_owners=["fixture"],
        )
        self.assertTrue(Path(advanced["last_good_path"]).is_file())

        rolled_back = exact.rollback(destination)
        checked = exact.check(first, destination)

        self.assertEqual(
            rolled_back["projection_digest"],
            first.projection_digest,
        )
        self.assertEqual(
            checked["counts"]["documents"],
            first.manifest["files"]["documents"]["record_count"],
        )
        self.assertTrue(Path(rolled_back["last_good_path"]).is_file())

    def test_sqlite_record_index_covers_every_base_record_class(self) -> None:
        destination = self.root / "runtime" / "repo-self.sqlite3"
        result = exact.materialize(self.bundle, destination)
        self.assertEqual(result["counts"]["records"], 6)
        connection = sqlite3.connect(destination)
        connection.row_factory = sqlite3.Row
        try:
            classes = {row[1] for row in exact.record_kinds(connection)}
            searches = {
                node_class: exact.search_records_lexical(
                    connection,
                    query,
                    node_class=node_class,
                    limit=2,
                )[0]
                for node_class, query in {
                    "entity": "repository owner route",
                    "event": "release observed history",
                    "assertion": "owned fixture assertion",
                    "relation": "contains introduction relation",
                }.items()
            }
            relation = exact.read_record(
                connection,
                "aoa:fixture:relation:contains",
            )
        finally:
            connection.close()
        self.assertEqual(
            classes,
            {"anchor", "artifact", "assertion", "entity", "event", "relation"},
        )
        self.assertTrue(all(searches.values()))
        self.assertEqual(relation["relation_kind"], "contains")

    def test_record_read_keeps_document_text_behind_document_resources(self) -> None:
        destination = self.root / "runtime" / "repo-self.sqlite3"
        exact.materialize(self.bundle, destination)
        config = replace(
            RuntimeConfig.discover(stack_root=self.root),
            sqlite_path=destination,
        )
        application = KagApplication(config=config)

        result = application.read(
            "aoa-kag://records/aoa%3Afixture%3Aanchor%3Aintro",
            detail="full",
        )
        payload = result["resource"]["payload"]

        self.assertEqual(payload["document_count"], 1)
        self.assertEqual(len(payload["documents"]), 1)
        self.assertIn("snippet", payload["documents"][0])
        self.assertNotIn("text", payload["documents"][0])

    def test_agent_result_pages_are_bounded_to_ten_records(self) -> None:
        application = KagApplication()

        with self.assertRaisesRegex(ValueError, "from 1 through 10"):
            application.search("repository", limit=11)
        with self.assertRaisesRegex(ValueError, "from 1 through 10"):
            application.traverse(["aoa:fixture:entity:repository"], limit=11)

    def test_indexed_unicode_controls_are_reported_as_data_findings(self) -> None:
        payload = KagApplication._bounded_payload(
            {"text": "report\u202etxt role\u200badmin"}
        )

        inspection = payload["content_inspection"]
        self.assertEqual(inspection["state"], "flagged")
        self.assertEqual(
            [item["code_point"] for item in inspection["findings"]],
            ["U+202E", "U+200B"],
        )

    def test_record_kind_discovery_respects_access_scope(self) -> None:
        destination = self.root / "runtime" / "repo-self.sqlite3"
        exact.materialize(self.bundle, destination)
        connection = sqlite3.connect(destination)
        connection.row_factory = sqlite3.Row
        try:
            source = connection.execute(
                "SELECT * FROM records WHERE node_class='artifact' LIMIT 1"
            ).fetchone()
            values = dict(source)
            values.update(
                {
                    "id": "aoa:fixture:artifact:private",
                    "kind": "secret_record",
                    "label": "Private record",
                    "access_scope": "private",
                }
            )
            payload = json.loads(values["payload_json"])
            payload.update(
                {
                    "id": values["id"],
                    "kind": values["kind"],
                    "label": values["label"],
                    "access_scope": values["access_scope"],
                }
            )
            values["payload_json"] = canonical_json(payload)
            columns = list(values)
            connection.execute(
                f"INSERT INTO records ({','.join(columns)}) VALUES "
                f"({','.join('?' for _ in columns)})",
                [values[column] for column in columns],
            )
            connection.commit()

            public_kinds = exact.record_kinds(connection)
            private_kinds = exact.record_kinds(
                connection,
                access_scopes=("private",),
            )
        finally:
            connection.close()

        self.assertNotIn(("fixture", "artifact", "secret_record"), public_kinds)
        self.assertIn(("fixture", "artifact", "secret_record"), private_kinds)

    def test_runtime_query_failure_returns_bounded_degradation(self) -> None:
        config = replace(
            RuntimeConfig.discover(stack_root=self.root),
            sqlite_path=self.root / "missing.sqlite3",
        )
        application = KagApplication(config=config)
        with mock.patch.object(
            application,
            "_runtime_hits",
            side_effect=sqlite3.OperationalError("interrupted"),
        ):
            result = application.search(
                "repository owner route",
                strategy="lexical",
            )
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["results"], [])
        self.assertEqual(
            result["route"]["degradation"],
            [
                {
                    "target": "runtime",
                    "state": "unavailable",
                    "fallback": "empty-bounded-result",
                    "reason": "OperationalError",
                }
            ],
        )

    def test_tiered_distribution_identity_and_degradation_reach_mcp_results(
        self,
    ) -> None:
        destination = self.root / "runtime" / "repo-self.sqlite3"
        exact.materialize(self.bundle, destination)
        config = replace(
            RuntimeConfig.discover(stack_root=self.root),
            sqlite_path=destination,
        )
        write_json_atomic(
            config.distribution_path,
            {
                "schema_version": ("abyss-stack-kag-tiered-distribution-current-v1"),
                "updated_at": "2026-07-18T00:00:00Z",
                "state": "hot_only",
                "composition_identity": None,
                "owners": [
                    {
                        "owner": "fixture",
                        "source_ref": "commit:" + ("a" * 40),
                        "release_digest": "sha256:" + ("b" * 64),
                        "corpus_digest": "sha256:" + ("c" * 64),
                        "distribution_digest": "sha256:" + ("d" * 64),
                        "delivery_state": "complete",
                    }
                ],
                "candidates": [],
                "summary": {
                    "active_owner_count": 1,
                    "candidate_owner_count": 0,
                    "composition_active": False,
                },
                "degradation": [
                    {
                        "target": "tiered-distribution",
                        "state": "hot_only",
                        "fallback": "last-good-projection-or-git-hot",
                    }
                ],
            },
        )
        application = KagApplication(config=config)

        discovered = application.discover(detail="full")
        result = application.search(
            "README.md",
            strategy="exact",
            owner="fixture",
            record_class="artifact",
        )

        self.assertEqual(discovered["distribution"]["state"], "hot_only")
        self.assertEqual(discovered["degradation"][0]["target"], "tiered-distribution")
        self.assertEqual(result["status"], "degraded")
        self.assertIn(
            {
                "target": "tiered-distribution",
                "state": "hot_only",
                "fallback": "last-good-projection-or-git-hot",
            },
            result["route"]["degradation"],
        )
        self.assertEqual(
            result["results"][0]["corpus_identity"]["content_digest"],
            "sha256:" + ("c" * 64),
        )
        self.assertEqual(
            result["results"][0]["distribution_identity"]["content_digest"],
            "sha256:" + ("d" * 64),
        )

    def test_self_described_exact_projection_reports_missing_runtime_state(
        self,
    ) -> None:
        destination = self.root / "runtime" / "repo-self.sqlite3"
        exact.materialize(self.bundle, destination)
        config = replace(
            RuntimeConfig.discover(stack_root=self.root),
            sqlite_path=destination,
        )
        application = KagApplication(config=config)

        result = application.search(
            "README.md",
            strategy="exact",
            record_class="artifact",
        )

        self.assertEqual(result["status"], "degraded")
        self.assertIn(
            {
                "target": "runtime-projection-state",
                "state": "mismatched",
                "fallback": "sqlite-self-described-projection",
            },
            result["route"]["degradation"],
        )
        self.assertEqual(
            result["results"][0]["qualified_id"],
            "aoa:fixture:artifact:readme",
        )

    def test_owner_source_failure_degrades_freshness_without_hiding_runtime(
        self,
    ) -> None:
        destination = self.root / "runtime" / "repo-self.sqlite3"
        exact.materialize(self.bundle, destination)
        config = replace(
            RuntimeConfig.discover(stack_root=self.root),
            sqlite_path=destination,
        )
        canonical = mock.Mock()
        canonical.owner_digest.side_effect = ValueError("escaped owner route")
        application = KagApplication(config=config, canonical=canonical)

        result = application.discover(owner="fixture", detail="full")

        self.assertEqual([item["repo"] for item in result["owners"]], ["fixture"])
        self.assertEqual(
            result["owners"][0]["freshness"],
            {
                "state": "source_unavailable",
                "runtime_source_digest": _digest("source"),
                "canonical_source_digest": "",
                "canonical_error": "ValueError",
            },
        )

    def test_owner_discovery_reports_canonical_fallback_capabilities(self) -> None:
        config = RuntimeConfig.discover(stack_root=self.root)
        canonical = mock.Mock()
        canonical.owner_names.return_value = ["fixture"]
        canonical.owner_digest.return_value = _digest("source")
        canonical.discover_owner.return_value = {
            "kind_counts": {
                "artifact": {"document": 2},
                "entity": {"repository": 1},
            }
        }
        application = KagApplication(config=config, canonical=canonical)

        result = application.discover(owner="fixture", detail="full")
        strategies = {item["name"]: item for item in result["strategies"]}

        self.assertTrue(strategies["exact"]["available"])
        self.assertTrue(strategies["lexical"]["available"])
        self.assertEqual(result["kinds"]["artifact"], ["document"])
        self.assertEqual(result["kinds"]["entity"], ["repository"])

    def test_qualified_owner_survives_canonical_route_failure(self) -> None:
        canonical = mock.Mock()
        canonical.resolve_owner.side_effect = OSError("owner map unavailable")
        application = KagApplication(canonical=canonical)

        owner = application._record_owner("aoa:fixture:artifact:readme")

        self.assertEqual(owner, "fixture")

    def test_result_merges_return_each_qualified_record_once(self) -> None:
        documents = [
            {"id": "aoa:fixture:anchor:a", "document_id": "document:a:1"},
            {"id": "aoa:fixture:anchor:a", "document_id": "document:a:2"},
            {"id": "aoa:fixture:anchor:b", "document_id": "document:b:1"},
        ]
        records = [
            {"id": "aoa:fixture:anchor:a"},
            {"id": "aoa:fixture:entity:c"},
        ]

        exact_hits = KagApplication._merge_exact_hits(
            documents, records, offset=0, limit=10
        )
        lexical_hits = KagApplication._merge_lexical_hits(
            documents, records, offset=0, limit=10
        )
        hybrid_hits = KagApplication._hybrid(
            lexical=[documents[0], documents[1]],
            semantic=[documents[1], documents[2]],
            limit=10,
        )

        self.assertEqual(
            [item["id"] for item in exact_hits],
            [
                "aoa:fixture:anchor:a",
                "aoa:fixture:entity:c",
                "aoa:fixture:anchor:b",
            ],
        )
        self.assertEqual(len({item["id"] for item in lexical_hits}), 3)
        self.assertEqual(
            [item["id"] for item in hybrid_hits],
            ["aoa:fixture:anchor:a", "aoa:fixture:anchor:b"],
        )
        self.assertEqual(
            set(hybrid_hits[0]["hybrid_components"]), {"lexical", "semantic"}
        )

    def test_missing_graph_projection_uses_exact_relation_paths(self) -> None:
        sqlite_path = self.root / "repo-self.sqlite3"
        exact.materialize(self.bundle, sqlite_path)
        config = replace(
            RuntimeConfig.discover(stack_root=self.root),
            sqlite_path=sqlite_path,
        )
        config.current_path.parent.mkdir(parents=True)
        config.current_path.write_text(
            json.dumps(
                {
                    "projection_identity": {
                        "content_digest": self.bundle.projection_digest
                    },
                    "targets": {"graph": {"status": "missing"}},
                }
            ),
            encoding="utf-8",
        )
        application = KagApplication(config=config)
        graph_capability = next(
            item
            for item in application.discover()["strategies"]
            if item["name"] == "graph"
        )
        result = application.traverse(
            ["aoa:fixture:artifact:readme"],
            owner="fixture",
            max_depth=2,
        )
        self.assertTrue(graph_capability["available"])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(
            result["route"]["adapters"][0]["adapter"],
            "sqlite-exact-relations",
        )
        self.assertEqual(
            [item["qualified_id"] for item in result["results"]],
            ["aoa:fixture:anchor:intro"],
        )
        evidence = result["results"][0]["evidence_path"]
        self.assertEqual(evidence["depth"], 1)
        self.assertEqual(
            [item["id"] for item in evidence["relations"]],
            ["aoa:fixture:relation:contains"],
        )

    def test_graph_results_are_enriched_from_exact_records(self) -> None:
        sqlite_path = self.root / "repo-self.sqlite3"
        exact.materialize(self.bundle, sqlite_path)
        config = replace(
            RuntimeConfig.discover(stack_root=self.root),
            sqlite_path=sqlite_path,
        )
        config.current_path.parent.mkdir(parents=True)
        config.current_path.write_text(
            json.dumps(
                {
                    "projection_identity": {
                        "content_digest": self.bundle.projection_digest
                    },
                    "targets": {"graph": {"status": "current"}},
                }
            ),
            encoding="utf-8",
        )
        graph_hit = {
            "id": "aoa:fixture:entity:repository",
            "repo": "fixture",
            "namespace": "aoa:fixture",
            "node_class": "entity",
            "kind": "repository",
            "access": {"scope": "public"},
            "evidence_path": {
                "source_id": "aoa:fixture:artifact:readme",
                "target_id": "aoa:fixture:entity:repository",
                "depth": 1,
                "nodes": [],
                "relations": [],
            },
        }
        application = KagApplication(config=config)

        with (
            mock.patch(
                "kag_runtime.application._neo4j_headers",
                return_value={},
            ),
            mock.patch.object(
                graph,
                "traverse",
                return_value=([graph_hit], 1.0),
            ),
        ):
            result = application.traverse(
                ["aoa:fixture:artifact:readme"],
                detail="full",
            )

        hit = result["results"][0]
        self.assertEqual(hit["label"], "Fixture repository")
        self.assertEqual(hit["path"], "README.md")
        self.assertEqual(hit["record"]["id"], hit["qualified_id"])

    def test_application_routes_graph_reads_through_owner_slices(self) -> None:
        sqlite_path = self.root / "repo-self.sqlite3"
        exact.materialize(self.bundle, sqlite_path)
        config = replace(
            RuntimeConfig.discover(stack_root=self.root),
            sqlite_path=sqlite_path,
        )
        config.current_path.parent.mkdir(parents=True)
        graph_result = {
            "storage_mode": "owner_slices",
            "owner_slices": {"fixture": "owner-slice-a"},
            "relation_slices": ["relation-slice-a"],
        }
        config.current_path.write_text(
            json.dumps(
                {
                    "projection_identity": {
                        "content_digest": self.bundle.projection_digest
                    },
                    "targets": {
                        "graph": {
                            "status": "current",
                            "result": graph_result,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        application = KagApplication(config=config)
        with (
            mock.patch(
                "kag_runtime.application._neo4j_headers",
                return_value={},
            ),
            mock.patch.object(
                graph,
                "traverse",
                return_value=([], 1.0),
            ) as traversal,
        ):
            result = application.traverse(
                ["aoa:fixture:artifact:readme"],
                owner="fixture",
            )

        self.assertEqual(
            traversal.call_args.kwargs["owner_slice_state"],
            graph_result,
        )
        self.assertEqual(
            result["route"]["adapters"][0]["adapter"],
            "neo4j-owner-slices",
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

    def test_qdrant_projection_cleanup_stays_with_its_alias(self) -> None:
        qdrant = FakeQdrant()
        old_active = f"{vector.COLLECTION_PREFIX}old-active"
        other_profile = f"{vector.COLLECTION_PREFIX}other-profile"
        for name in (old_active, other_profile):
            qdrant.collections[name] = {
                "count": 0,
                "size": 3,
                "distance": "Cosine",
                "payload_schema": {},
                "points": {},
            }
        qdrant.aliases.update(
            {
                "lab-active": old_active,
                "lab-other": other_profile,
            }
        )

        result = vector.materialize(
            self.bundle,
            qdrant=qdrant,
            embeddings=FakeEmbeddings(),
            alias="lab-active",
        )

        self.assertNotIn(old_active, qdrant.collections)
        self.assertEqual(result["removed_collections"], [old_active])
        self.assertIn(other_profile, qdrant.collections)
        self.assertEqual(qdrant.aliases["lab-other"], other_profile)

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
            [
                {"key": "access.scope", "match": {"value": "public"}},
                {"key": "repo", "match": {"value": "fixture"}},
            ],
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

    def test_qdrant_owner_slices_update_only_affected_owner_collection(
        self,
    ) -> None:
        first = write_two_owner_bundle(self.root / "vector-two-owner")
        second = write_changed_owner_bundle(
            first,
            self.root / "vector-two-owner-next",
            owner="fixture",
            marker="vector-owner-marker",
        )
        state_path = self.root / "runtime" / "vector" / "owner-slices.json"
        qdrant = FakeQdrant()
        initial_embeddings = AdaptiveEmbeddings(max_batch_size=2)
        initial = vector.materialize_owner_slices(
            first,
            qdrant=qdrant,
            embeddings=initial_embeddings,
            state_path=state_path,
            batch_size=2,
        )
        unaffected_collection = initial["owner_collections"]["fixture-b"]
        affected_collection = initial["owner_collections"]["fixture"]
        initial_point_writes = len(qdrant.points)

        changed_embeddings = AdaptiveEmbeddings(max_batch_size=2)
        advanced = vector.materialize_owner_slices(
            second,
            qdrant=qdrant,
            embeddings=changed_embeddings,
            state_path=state_path,
            affected_owners=["fixture"],
            batch_size=2,
        )
        checked = vector.check_owner_slices(
            second,
            qdrant=qdrant,
            state_path=state_path,
        )
        rolled_back = vector.rollback_owner_slices(
            qdrant=qdrant,
            state_path=state_path,
        )
        rollback_checked = vector.check_owner_slices(
            first,
            qdrant=qdrant,
            state_path=state_path,
        )

        self.assertEqual(initial["owner_count"], 2)
        self.assertEqual(advanced["changed_owners"], ["fixture"])
        self.assertEqual(advanced["reused_owner_slices"], ["fixture-b"])
        self.assertEqual(
            advanced["owner_collections"]["fixture-b"],
            unaffected_collection,
        )
        self.assertNotEqual(
            advanced["owner_collections"]["fixture"],
            affected_collection,
        )
        self.assertEqual(
            changed_embeddings.texts, ["# Changed owner\nvector-owner-marker\n"]
        )
        self.assertEqual(len(qdrant.points), initial_point_writes + 1)
        self.assertEqual(checked["point_count"], 2)
        self.assertEqual(
            rolled_back["projection_digest"],
            first.projection_digest,
        )
        self.assertEqual(
            rollback_checked["owner_collections"]["fixture"],
            affected_collection,
        )

    def test_qdrant_owner_slice_search_embeds_once_across_owner_fanout(
        self,
    ) -> None:
        bundle = write_two_owner_bundle(self.root / "vector-search-two-owner")
        state_path = self.root / "runtime" / "vector" / "owner-slices.json"
        qdrant = FakeQdrant()
        vector.materialize_owner_slices(
            bundle,
            qdrant=qdrant,
            embeddings=AdaptiveEmbeddings(max_batch_size=2),
            state_path=state_path,
            batch_size=2,
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        embeddings = AdaptiveEmbeddings(max_batch_size=2)

        points, _ = vector.search_owner_slices(
            "repository evidence",
            qdrant=qdrant,
            embeddings=embeddings,
            profile=state["embedding_profile"],
            owner_collections={
                owner: packet["collection"] for owner, packet in state["owners"].items()
            },
            limit=10,
        )

        self.assertEqual(len(points), 2)
        self.assertEqual(len(embeddings.texts), 1)
        self.assertEqual(len(qdrant.queries), 2)

    def test_application_routes_semantic_reads_through_owner_slices(self) -> None:
        state_path = self.root / "runtime" / "vector" / "owner-slices.json"
        qdrant = FakeQdrant()
        vector_result = vector.materialize_owner_slices(
            self.bundle,
            qdrant=qdrant,
            embeddings=FakeEmbeddings(),
            state_path=state_path,
        )
        config = RuntimeConfig.discover(stack_root=self.root)
        config.current_path.parent.mkdir(parents=True)
        config.current_path.write_text(
            json.dumps(
                {
                    "projection_identity": {
                        "content_digest": self.bundle.projection_digest
                    },
                    "targets": {
                        "vector": {
                            "status": "current",
                            "result": vector_result,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        application = KagApplication(config=config)

        with mock.patch(
            "kag_runtime.application.JsonHttpClient",
            side_effect=[qdrant, FakeEmbeddings()],
        ):
            result = application.search(
                "repository evidence",
                strategy="semantic",
                owner="fixture",
            )

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(
            result["route"]["adapters"][0]["adapter"],
            "qdrant-owner-slices",
        )
        self.assertEqual(result["results"][0]["owner"]["repo"], "fixture")

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
        embeddings = AdaptiveEmbeddings(max_batch_size=1)

        result = vector.materialize(
            bundle,
            qdrant=qdrant,
            embeddings=embeddings,
        )

        self.assertEqual(result["embedded_point_count"], len(documents))
        self.assertEqual(embeddings.batch_sizes, [1] * len(documents))
        self.assertEqual(
            embeddings.texts,
            [document["text"] for document in documents],
        )

    def test_neo4j_projection_switches_current_after_complete_counts(self) -> None:
        fake = FakeGraph()
        result = graph.materialize(self.bundle, graph=fake, batch_size=1)
        self.assertEqual(result["counts"]["nodes"], 5)
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
            "nodes": 5,
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

    def test_neo4j_projection_retains_other_runtime_channels(self) -> None:
        fake = FakeGraph()
        fake.current = self.bundle.projection_digest
        fake.previous = "previous-projection"
        fake.retained_digests = ["other-channel-current"]
        fake.counts = {
            "owners": 1,
            "nodes": 5,
            "relations": 1,
            "external_references": 1,
        }
        fake.stale_nodes = 1

        result = graph.materialize(self.bundle, graph=fake, batch_size=1000)

        self.assertIn("other-channel-current", result["retained_projection_digests"])
        self.assertIn("other-channel-current", fake.cleanup_keep)
        self.assertTrue(
            all(channel == graph.DEFAULT_CHANNEL for channel in fake.observed_channels)
        )

    def test_neo4j_owner_slices_update_only_affected_owner_and_relation_slices(
        self,
    ) -> None:
        first = write_two_owner_bundle(self.root / "graph-two-owner")
        second = write_changed_owner_bundle(
            first,
            self.root / "graph-two-owner-next",
            owner="fixture",
            marker="graph-owner-marker",
        )
        state_path = self.root / "runtime" / "graph" / "owner-slices.json"
        fake = FakeGraph()
        initial = graph.materialize_owner_slices(
            first,
            graph=fake,
            state_path=state_path,
            batch_size=2,
        )
        initial_relations = set(initial["relation_slices"])

        advanced = graph.materialize_owner_slices(
            second,
            graph=fake,
            state_path=state_path,
            affected_owners=["fixture"],
            batch_size=2,
        )
        checked = graph.check_owner_slices(
            second,
            graph=fake,
            state_path=state_path,
        )
        rolled_back = graph.rollback_owner_slices(
            graph=fake,
            state_path=state_path,
        )
        rollback_checked = graph.check_owner_slices(
            first,
            graph=fake,
            state_path=state_path,
        )

        self.assertEqual(initial["counts"]["owners"], 2)
        self.assertEqual(advanced["changed_owners"], ["fixture"])
        self.assertEqual(advanced["reused_owner_slices"], ["fixture-b"])
        self.assertEqual(
            advanced["owner_slices"]["fixture-b"],
            initial["owner_slices"]["fixture-b"],
        )
        self.assertNotEqual(
            advanced["owner_slices"]["fixture"],
            initial["owner_slices"]["fixture"],
        )
        self.assertEqual(
            len(initial_relations.intersection(advanced["relation_slices"])),
            1,
        )
        self.assertEqual(checked["counts"]["nodes"], 10)
        self.assertTrue((state_path.parent / "owner-slices.last-good.json").is_file())
        self.assertEqual(
            rolled_back["projection_digest"],
            first.projection_digest,
        )
        self.assertEqual(
            rollback_checked["owner_slices"]["fixture"],
            initial["owner_slices"]["fixture"],
        )

    def test_neo4j_owner_slice_traversal_is_bounded_to_active_slices(self) -> None:
        class TraversalGraph:
            def __init__(self) -> None:
                self.statement = ""
                self.parameters: dict[str, Any] = {}

            def execute(
                self,
                statement: str,
                parameters: dict[str, Any] | None = None,
            ) -> list[list[Any]]:
                self.statement = statement
                self.parameters = parameters or {}
                return [
                    [
                        "aoa:fixture:artifact:readme",
                        "aoa:fixture:anchor:intro",
                        "fixture",
                        "aoa:fixture",
                        "anchor",
                        "markdown_heading",
                        ["source:readme"],
                        ["aoa:fixture:anchor:intro"],
                        "public",
                        1,
                        [],
                        [
                            {
                                "id": "aoa:fixture:relation:contains",
                                "evidence_anchor_ids": ["aoa:fixture:anchor:intro"],
                            }
                        ],
                    ]
                ]

        fake = TraversalGraph()
        hits, _ = graph.traverse(
            graph=fake,  # type: ignore[arg-type]
            projection=self.bundle.projection_digest,
            owner_slice_state={
                "storage_mode": "owner_slices",
                "owner_slices": {"fixture": "owner-slice-a"},
                "relation_slices": ["relation-slice-a"],
            },
            source_ids=["aoa:fixture:artifact:readme"],
            max_depth=2,
        )

        self.assertIn("AoAKagNodeSlice", fake.statement)
        self.assertIn("AOA_KAG_RELATION_SLICE", fake.statement)
        self.assertEqual(fake.parameters["owner_slices"], ["owner-slice-a"])
        self.assertEqual(fake.parameters["relation_slices"], ["relation-slice-a"])
        self.assertEqual(hits[0]["id"], "aoa:fixture:anchor:intro")

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

    def test_root_command_executes_owner_incremental_exact_update(self) -> None:
        first = write_two_owner_bundle(self.root / "command-two-owner")
        second = write_changed_owner_bundle(
            first,
            self.root / "command-two-owner-next",
            owner="fixture",
            marker="command-owner-marker",
        )
        stack_root = self.root / "stack"
        command = REPO_ROOT / "scripts" / "aoa-kag-runtime-projection"
        base_args = [
            sys.executable,
            str(command),
            "--stack-root",
            str(stack_root),
            "--target",
            "exact",
        ]
        initial = subprocess.run(
            [*base_args, "--bundle-dir", str(first.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(initial.returncode, 0, msg=initial.stderr)
        advanced = subprocess.run(
            [
                *base_args,
                "--bundle-dir",
                str(second.root),
                "--affected-owner",
                "fixture",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(advanced.returncode, 0, msg=advanced.stderr)
        report = json.loads(advanced.stdout[advanced.stdout.index("{") :])
        self.assertEqual(
            report["targets"]["exact"]["update_mode"],
            "owner_incremental",
        )
        current = json.loads(
            (stack_root / "Knowledge" / "kag" / "repo-self" / "current.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            current["targets"]["exact"]["result"]["affected_owners"],
            ["fixture"],
        )

    def test_root_command_coordinates_matching_projection_rollback(self) -> None:
        stack_root = self.root / "stack"
        identity = {
            "projection_digest": _digest("rollback-projection"),
            "bundle_digest": _digest("rollback-bundle"),
            "federation_digest": _digest("rollback-federation"),
        }
        exact_result = {**identity, "schema_version": exact.SCHEMA_VERSION}
        vector_result = {
            **identity,
            "schema_version": vector.OWNER_SLICE_SCHEMA_VERSION,
            "storage_mode": "owner_slices",
        }
        graph_result = {
            **identity,
            "schema_version": graph.OWNER_SLICE_SCHEMA_VERSION,
            "storage_mode": "owner_slices",
        }

        with (
            mock.patch.object(
                runtime_projection.exact,
                "rollback_candidate",
                return_value=identity,
            ),
            mock.patch.object(
                runtime_projection.vector,
                "owner_slice_rollback_candidate",
                return_value=identity,
            ),
            mock.patch.object(
                runtime_projection.graph,
                "owner_slice_rollback_candidate",
                return_value=identity,
            ),
            mock.patch.object(
                runtime_projection.exact,
                "rollback",
                return_value=exact_result,
            ),
            mock.patch.object(
                runtime_projection.vector,
                "rollback_owner_slices",
                return_value=vector_result,
            ),
            mock.patch.object(
                runtime_projection.graph,
                "rollback_owner_slices",
                return_value=graph_result,
            ),
            mock.patch.object(
                runtime_projection,
                "_neo4j_headers",
                return_value={},
            ),
            mock.patch.object(runtime_projection, "JsonHttpClient"),
            mock.patch.object(runtime_projection.graph, "Neo4jProjection"),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = runtime_projection.main(
                    [
                        "--stack-root",
                        str(stack_root),
                        "--target",
                        "all",
                        "--owner-scoped",
                        "--rollback",
                    ]
                )

        self.assertEqual(result, 0)
        self.assertEqual(
            json.loads(output.getvalue())["schema_version"],
            "abyss-stack-repo-self-kag-projection-rollback-receipt-v1",
        )
        current = json.loads(
            (stack_root / "Knowledge" / "kag" / "repo-self" / "current.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            current["projection_identity"]["content_digest"],
            identity["projection_digest"],
        )
        self.assertEqual(set(current["targets"]), {"exact", "vector", "graph"})

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
