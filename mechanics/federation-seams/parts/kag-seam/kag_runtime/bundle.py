from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping


ZERO_DIGEST = "0" * 64
BUNDLE_SCHEMA_VERSION = "aoa-repo-local-kag-retrieval-bundle-v1"
EXPECTED_FILES = {
    "owners": "owners.jsonl",
    "nodes": "nodes.jsonl",
    "relations": "relations.jsonl",
    "external_references": "external_references.jsonl",
    "documents": "documents.jsonl",
}
_DIGEST_URI_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class BundleError(RuntimeError):
    pass


def canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _object(payload: object, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BundleError(f"{label} must be a JSON object")
    return payload


@dataclass(frozen=True)
class RetrievalBundle:
    root: Path
    manifest: dict[str, Any]

    @classmethod
    def open(cls, root: Path) -> "RetrievalBundle":
        resolved = root.resolve()
        manifest_path = resolved / "manifest.json"
        try:
            manifest = _object(
                json.loads(manifest_path.read_text(encoding="utf-8")),
                "retrieval bundle manifest",
            )
        except FileNotFoundError as exc:
            raise BundleError(f"missing retrieval bundle manifest: {manifest_path}") from exc
        except json.JSONDecodeError as exc:
            raise BundleError(f"invalid retrieval bundle manifest: {exc}") from exc
        return cls(resolved, manifest)

    @property
    def projection_digest(self) -> str:
        return str(self.manifest["projection_identity"]["content_digest"])

    @property
    def federation_digest(self) -> str:
        return str(self.manifest["federation_identity"]["content_digest"])

    @property
    def bundle_digest(self) -> str:
        return str(self.manifest["bundle_identity"]["content_digest"])

    def path(self, key: str) -> Path:
        metadata = _object(self.manifest["files"].get(key), f"files.{key}")
        relative = str(metadata.get("path", ""))
        if relative != EXPECTED_FILES.get(key):
            raise BundleError(f"files.{key}.path must be {EXPECTED_FILES.get(key)}")
        return self.root / relative

    def records(self, key: str) -> Iterator[dict[str, Any]]:
        path = self.path(key)
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        raise BundleError(f"{path}:{line_number} is blank")
                    try:
                        yield _object(
                            json.loads(line),
                            f"{path}:{line_number}",
                        )
                    except json.JSONDecodeError as exc:
                        raise BundleError(f"{path}:{line_number}: {exc}") from exc
        except FileNotFoundError as exc:
            raise BundleError(f"missing retrieval bundle file: {path}") from exc

    def verify(self) -> dict[str, Any]:
        if self.manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
            raise BundleError(f"unsupported retrieval bundle schema: {self.manifest.get('schema_version')}")
        if set(_object(self.manifest.get("files"), "files")) != set(EXPECTED_FILES):
            raise BundleError("retrieval bundle file set is incomplete")
        if self.manifest.get("projection_lanes") != [
            "exact",
            "lexical",
            "vector",
            "hybrid",
            "graph",
        ]:
            raise BundleError("retrieval bundle projection lanes are out of contract")

        material = copy.deepcopy(self.manifest)
        identity = _object(material.get("bundle_identity"), "bundle_identity")
        observed_bundle_digest = str(identity.get("content_digest", ""))
        identity["content_digest"] = ZERO_DIGEST
        expected_bundle_digest = hashlib.sha256(
            canonical_json(material).encode("utf-8")
        ).hexdigest()
        if observed_bundle_digest != expected_bundle_digest:
            raise BundleError("retrieval bundle identity digest mismatch")

        retrieval_profile = _object(
            self.manifest.get("retrieval_profile"),
            "retrieval_profile",
        )
        raw_max_chunk_chars = retrieval_profile.get("max_chunk_chars")
        max_chunk_chars = (
            int(raw_max_chunk_chars)
            if isinstance(raw_max_chunk_chars, int) and raw_max_chunk_chars > 0
            else None
        )
        files: dict[str, dict[str, Any]] = {}
        for key, expected_path in EXPECTED_FILES.items():
            metadata = _object(self.manifest["files"].get(key), f"files.{key}")
            if metadata.get("path") != expected_path:
                raise BundleError(f"files.{key}.path must be {expected_path}")
            path = self.path(key)
            digest = hashlib.sha256()
            size = 0
            count = 0
            try:
                with path.open("rb") as handle:
                    for line_number, raw_line in enumerate(handle, 1):
                        digest.update(raw_line)
                        size += len(raw_line)
                        if not raw_line.strip():
                            raise BundleError(f"{path}:{line_number} is blank")
                        try:
                            record = _object(
                                json.loads(raw_line),
                                f"{path}:{line_number}",
                            )
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise BundleError(f"{path}:{line_number}: {exc}") from exc
                        if key == "documents":
                            text = record.get("text")
                            if not isinstance(text, str) or not text:
                                raise BundleError(
                                    f"{path}:{line_number}: document text must be non-empty"
                                )
                            if max_chunk_chars is not None and len(text) > max_chunk_chars:
                                raise BundleError(
                                    f"{path}:{line_number}: document text exceeds max_chunk_chars"
                                )
                            for field in ("document_role", "surface_state"):
                                if not isinstance(record.get(field), str) or not record[field]:
                                    raise BundleError(
                                        f"{path}:{line_number}: {field} must be non-empty"
                                    )
                        elif key in {"nodes", "relations"}:
                            if record.get("record_form") not in {
                                "projection_handle",
                                "canonical_record",
                                "federated_projection",
                            }:
                                raise BundleError(
                                    f"{path}:{line_number}: record_form is invalid"
                                )
                            for field in (
                                "label",
                                "search_text",
                                "document_role",
                                "surface_state",
                                "access_scope",
                                "provenance_ref",
                                "temporal_ref",
                                "trust_ref",
                            ):
                                if not isinstance(record.get(field), str) or not record[field]:
                                    raise BundleError(
                                        f"{path}:{line_number}: {field} must be non-empty"
                                    )
                            if not isinstance(record.get("path"), str):
                                raise BundleError(
                                    f"{path}:{line_number}: path must be a string"
                                )
                        count += 1
            except FileNotFoundError as exc:
                raise BundleError(f"missing retrieval bundle file: {path}") from exc
            if digest.hexdigest() != metadata.get("sha256"):
                raise BundleError(f"{expected_path} digest mismatch")
            if size != metadata.get("bytes"):
                raise BundleError(f"{expected_path} byte count mismatch")
            if count != metadata.get("record_count"):
                raise BundleError(f"{expected_path} record count mismatch")
            files[key] = {
                "sha256": digest.hexdigest(),
                "bytes": size,
                "record_count": count,
            }

        summary = _object(self.manifest.get("summary"), "summary")
        federation_summary = _object(
            self.manifest.get("federation_summary"),
            "federation_summary",
        )
        expected_counts = {
            "owners": federation_summary.get("owner_count"),
            "nodes": federation_summary.get("node_count"),
            "relations": federation_summary.get("relation_count"),
            "external_references": federation_summary.get("external_reference_count"),
            "documents": summary.get("document_count"),
        }
        for key, expected in expected_counts.items():
            if files[key]["record_count"] != expected:
                raise BundleError(f"{key} count disagrees with bundle summary")
        if federation_summary.get("unresolved_reference_count") != 0:
            raise BundleError("retrieval bundle contains unresolved references")
        if len(self.manifest.get("canonical_inputs", [])) != files["owners"]["record_count"]:
            raise BundleError("canonical input count disagrees with owner count")
        owners: set[str] = set()
        for index, raw_input in enumerate(self.manifest.get("canonical_inputs", [])):
            canonical_input = _object(raw_input, f"canonical_inputs[{index}]")
            repo = _object(
                canonical_input.get("repo"),
                f"canonical_inputs[{index}].repo",
            )
            owner = repo.get("name")
            if not isinstance(owner, str) or not owner or owner in owners:
                raise BundleError("canonical input owners must be unique and non-empty")
            owners.add(owner)
            corpus = _object(
                canonical_input.get("corpus_identity"),
                f"canonical_inputs[{index}].corpus_identity",
            )
            distribution = _object(
                canonical_input.get("distribution_identity"),
                f"canonical_inputs[{index}].distribution_identity",
            )
            for label, identity in (
                ("corpus", corpus),
                ("distribution", distribution),
            ):
                if _DIGEST_URI_RE.fullmatch(
                    str(identity.get("content_digest") or "")
                ) is None:
                    raise BundleError(
                        f"canonical input {owner} {label} identity is invalid"
                    )
            state = distribution.get("delivery_state")
            if not isinstance(state, str) or not state:
                raise BundleError(
                    f"canonical input {owner} delivery state is missing"
                )
            if not isinstance(distribution.get("complete"), bool):
                raise BundleError(
                    f"canonical input {owner} completeness is missing"
                )
            routes = distribution.get("routes")
            if not isinstance(routes, dict) or any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
                for value in routes.values()
            ):
                raise BundleError(
                    f"canonical input {owner} delivery routes are invalid"
                )

        return {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "bundle_digest": self.bundle_digest,
            "projection_digest": self.projection_digest,
            "federation_digest": self.federation_digest,
            "owners": sorted(owners),
            "files": files,
        }
