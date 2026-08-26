#!/usr/bin/env python3
"""Deterministic closure for evidence refs nested in prior actor returns.

The runtime may use this module only for an independent reviewer.  It never
rewrites a producer artifact and never treats the derivative namespace as
source authority.  Instead it proves a narrow graph from an explicitly
admitted producer task/result/report/delta to the exact historical bytes that
the producer cited.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator

PART_ROOT = Path(__file__).resolve().parent
if str(PART_ROOT) not in sys.path:
    sys.path.insert(0, str(PART_ROOT))

from external_codex_projection import (  # noqa: E402
    ProjectionError,
    verify_review_state_seal,
)


SCHEMA_ROOT = PART_ROOT / "schemas"
ACTOR_INPUT_SCHEMA = SCHEMA_ROOT / "external-codex-actor-input-envelope.schema.json"
TASK_SCHEMA = SCHEMA_ROOT / "external-codex-task.schema.json"
REPORT_SCHEMA = SCHEMA_ROOT / "external-codex-report.schema.json"
RESULT_SCHEMA = SCHEMA_ROOT / "external-codex-result.schema.json"
ACTOR_MANIFEST_SCHEMA = (
    SCHEMA_ROOT / "external-codex-actor-workspace-manifest.schema.json"
)
ACTOR_DELTA_SCHEMA = SCHEMA_ROOT / "external-codex-actor-delta.schema.json"

ACTOR_INPUT_VERSION = "abyss_stack_external_codex_actor_input_envelope_v1"
TASK_VERSION = "abyss_stack_external_codex_task_v1"
REPORT_VERSION = "abyss_stack_external_codex_report_v1"
RESULT_VERSION = "abyss_stack_external_codex_result_v2"
DELTA_VERSION = "abyss_stack_external_codex_actor_delta_v1"
NAMESPACE_VERSION = "abyss_stack_external_codex_nested_evidence_namespace_v1"
MAX_BYTES = 16 * 1024 * 1024
MAX_EXCERPT_BYTES = 256 * 1024
MAX_NAMESPACE_BYTES = 4 * 1024 * 1024
LINE_ANCHOR_RE = re.compile(
    r"L(?P<start>[1-9][0-9]*)(?:-L(?P<end>[1-9][0-9]*))?"
)
TERMINAL_REPORT_PATH_RE = re.compile(
    r"^attempts/(?P<number>[0-9]+)/model-report\.json$"
)
SECRET_PATH_PARTS = {
    ".aws",
    ".docker",
    ".gnupg",
    ".kube",
    ".ssh",
    "credential",
    "credentials",
    "secret",
    "secrets",
}
SECRET_FILE_NAMES = {
    ".env",
    ".envrc",
    ".git-credentials",
    ".gitcookies",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".yarnrc",
    ".yarnrc.yml",
    "auth.json",
    "credentials.json",
    "id_dsa",
    "id_ed25519",
    "id_ecdsa",
    "id_rsa",
}
SECRET_FILE_TOKEN_RE = re.compile(
    r"(?:^|[._-])(?:api[-_]?key|client[-_]?secret|credential|credentials|"
    r"password|passwd|secret|secrets|token|tokens)(?:[._-]|$)",
    re.I,
)


class NestedEvidenceNamespaceError(ValueError):
    """One transitive evidence edge is absent, ambiguous, or drifted."""


@dataclass(frozen=True)
class _Record:
    input_id: str
    raw: bytes
    provenance: dict[str, Any]
    payload: Any

    @property
    def digest(self) -> str:
        return str(self.provenance["artifact_digest"])


@dataclass(frozen=True)
class _Producer:
    task: _Record
    result: _Record
    report: _Record
    delta: _Record
    outputs: tuple[_Record, ...]
    final_manifest: dict[str, Any]
    final_manifest_raw: bytes
    final_manifest_raw_digest: str
    workspace: Path
    terminal_attempt_id: str

    @property
    def task_id(self) -> str:
        return str(self.task.payload["task_id"])


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def nested_evidence_namespace_digest(value: Mapping[str, Any]) -> str:
    candidate = dict(value)
    candidate.pop("namespace_digest", None)
    return _sha256_bytes(_canonical_bytes(candidate))


def _read_regular(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise NestedEvidenceNamespaceError("evidence coordinate is not exact")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise NestedEvidenceNamespaceError("evidence coordinate is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
            raise NestedEvidenceNamespaceError("evidence coordinate is not bounded")
        chunks: list[bytes] = []
        remaining = MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_BYTES:
            raise NestedEvidenceNamespaceError("evidence coordinate is not bounded")
        return raw
    finally:
        os.close(descriptor)


def _json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NestedEvidenceNamespaceError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise NestedEvidenceNamespaceError(f"{label} is not a JSON object")
    return value


@lru_cache(maxsize=None)
def _schema(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    return _json_object(_read_regular(path), label=f"{path.name} schema")


def _validate_schema(value: Any, path: Path, *, label: str) -> None:
    schema = _schema(str(path))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        raise NestedEvidenceNamespaceError(f"{label} does not match its owner schema")


def _records(immutable_inputs: Sequence[Mapping[str, Any]]) -> list[_Record]:
    records: list[_Record] = []
    for item in immutable_inputs:
        input_id = str(item["input_id"])
        raw = bytes(item["raw"])
        raw_provenance = item["provenance"]
        provenance = (
            raw_provenance.model_dump(mode="json")
            if hasattr(raw_provenance, "model_dump")
            else dict(raw_provenance)
        )
        if _sha256_bytes(raw) != provenance.get("artifact_digest"):
            raise NestedEvidenceNamespaceError(
                f"review input bytes drifted before namespace closure: {input_id}"
            )
        try:
            payload: Any = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if (
            isinstance(payload, dict)
            and payload.get("schema_version") == ACTOR_INPUT_VERSION
        ):
            _validate_schema(payload, ACTOR_INPUT_SCHEMA, label="upstream actor envelope")
        records.append(_Record(input_id, raw, provenance, payload))
    return records


def _task_result_ref(result: _Record, task: _Record) -> dict[str, Any] | None:
    matches = [
        item
        for item in result.payload.get("evidence_refs", [])
        if (
            isinstance(item, dict)
            and item.get("artifact_digest") == task.digest
            and str(item.get("artifact_ref", "")).endswith("/inputs/task.json")
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _producer_projection(result: _Record) -> Path:
    projection = Path(str(result.payload.get("actor_projection_path", "")))
    if not projection.is_absolute():
        raise NestedEvidenceNamespaceError("producer runtime coordinate is not absolute")
    if _producer_review_seal(result) is not None:
        return projection
    try:
        resolved_projection = projection.resolve(strict=True)
    except OSError as exc:
        raise NestedEvidenceNamespaceError("producer actor projection is unavailable") from exc
    if (
        projection.is_symlink()
        or resolved_projection != projection
        or not projection.is_dir()
    ):
        raise NestedEvidenceNamespaceError("producer actor projection is not exact")
    return projection


def _producer_review_seal(
    result: _Record,
) -> tuple[Path, dict[str, Any]] | None:
    """Verify and return a producer's content-addressed terminal seal.

    New terminal writer results deliberately remain reviewable after their
    mutable actor projection changes or disappears.  The result coordinate is
    therefore semantic identity only once a seal is present; every source byte
    must come from the independently verified seal object store.
    """

    raw_ref = result.payload.get("review_seal_ref")
    if raw_ref is None:
        return None
    if not isinstance(raw_ref, dict) or raw_ref.get("owner_repo") != "abyss-stack":
        raise NestedEvidenceNamespaceError(
            "producer result has a malformed runtime-owned review seal"
        )
    projection = Path(str(result.payload.get("actor_projection_path", "")))
    seal_path = Path(str(raw_ref.get("artifact_ref", "")))
    if (
        not projection.is_absolute()
        or not seal_path.is_absolute()
        or seal_path.name != "review-state-seal.json"
        or seal_path.is_symlink()
        or not seal_path.is_file()
    ):
        raise NestedEvidenceNamespaceError(
            "producer review seal coordinate is unavailable or unsafe"
        )
    seal_root = seal_path.parent
    seal_base = projection.parent / "review-state-seal"
    first_attempt = seal_root == seal_base
    retry_attempt = (
        seal_root.parent == seal_base
        and re.fullmatch(r"attempt-[0-9]{3}", seal_root.name) is not None
    )
    seal_raw = _read_regular(seal_path)
    if (
        not (first_attempt or retry_attempt)
        or _sha256_bytes(seal_raw) != raw_ref.get("artifact_digest")
    ):
        raise NestedEvidenceNamespaceError(
            "producer review seal is not bound to its exact session"
        )
    try:
        metadata = verify_review_state_seal(
            seal_root,
            expected_session_id=str(result.payload.get("session_id", "")),
            expected_incarnation_id=str(result.payload.get("incarnation_id", "")),
            expected_status=str(result.payload.get("status", "")),
        )
    except ProjectionError as exc:
        raise NestedEvidenceNamespaceError(
            "producer review seal failed independent verification"
        ) from exc
    if metadata.get("projection_path") != str(projection):
        raise NestedEvidenceNamespaceError(
            "producer review seal names another actor projection"
        )
    return seal_root, metadata


def _verified_result_artifact(
    result: _Record,
    ref: Mapping[str, Any],
    *,
    label: str,
    expected_owner: str | None = None,
) -> tuple[Path, bytes]:
    projection = _producer_projection(result)
    session_root = projection.parent
    path = Path(str(ref.get("artifact_ref", "")))
    owner = ref.get("owner_repo")
    if (
        not path.is_absolute()
        or not isinstance(owner, str)
        or not owner
        or (expected_owner is not None and owner != expected_owner)
    ):
        raise NestedEvidenceNamespaceError(f"{label} ref is not runtime-owned")
    try:
        path.relative_to(session_root)
    except ValueError as exc:
        raise NestedEvidenceNamespaceError(f"{label} escapes the producer session") from exc
    raw = _read_regular(path)
    if _sha256_bytes(raw) != ref.get("artifact_digest"):
        raise NestedEvidenceNamespaceError(f"{label} bytes drifted")
    return path, raw


def _safe_result_final_manifest(
    result: _Record,
) -> tuple[dict[str, Any], bytes, str, Path]:
    result_payload = result.payload
    final_ref = result_payload.get("actor_final_manifest_ref")
    if not isinstance(final_ref, dict) or final_ref.get("owner_repo") != "abyss-stack":
        raise NestedEvidenceNamespaceError("producer result has no runtime-owned final manifest")
    projection = _producer_projection(result)
    review_seal = _producer_review_seal(result)
    expected_final_path = projection.parent / "actor-final-manifest.json"
    if review_seal is not None:
        seal_root, seal_metadata = review_seal
        expected_final_path = seal_root / str(seal_metadata["manifest_path"])
    final_path, final_raw = _verified_result_artifact(
        result,
        final_ref,
        label="producer final manifest",
        expected_owner="abyss-stack",
    )
    if final_path != expected_final_path:
        raise NestedEvidenceNamespaceError("producer final manifest escapes its session")
    final_manifest = _json_object(final_raw, label="producer final manifest")
    _validate_schema(
        final_manifest,
        ACTOR_MANIFEST_SCHEMA,
        label="producer final manifest",
    )
    if final_manifest.get("workspace_path") != str(projection):
        raise NestedEvidenceNamespaceError("producer final manifest names another projection")
    if review_seal is not None:
        seal_root, seal_metadata = review_seal
        delta_ref = result_payload.get("actor_delta_ref")
        if (
            str(final_ref.get("artifact_digest"))
            != str(seal_metadata.get("manifest_file_digest"))
            or not isinstance(delta_ref, dict)
            or delta_ref.get("owner_repo") != "abyss-stack"
            or Path(str(delta_ref.get("artifact_ref", "")))
            != seal_root / str(seal_metadata["delta_path"])
            or str(delta_ref.get("artifact_digest"))
            != str(seal_metadata.get("delta_file_digest"))
        ):
            raise NestedEvidenceNamespaceError(
                "producer final evidence is not bound into its review seal"
            )
    return final_manifest, final_raw, str(final_ref["artifact_digest"]), projection


def _terminal_attempt_id(result: _Record, report_path: Path) -> str:
    """Derive the terminal attempt from the result-bound model report path."""

    projection = _producer_projection(result)
    try:
        relative = report_path.relative_to(projection.parent).as_posix()
    except ValueError as exc:
        raise NestedEvidenceNamespaceError(
            "producer report does not bind a terminal attempt"
        ) from exc
    match = TERMINAL_REPORT_PATH_RE.fullmatch(relative)
    if match is None:
        raise NestedEvidenceNamespaceError(
            "producer report does not bind a terminal attempt"
        )
    attempt_number = int(match.group("number"))
    session_id = result.payload.get("session_id")
    attempt_count = result.payload.get("attempt_count")
    if (
        not isinstance(session_id, str)
        or not session_id
        or attempt_number < 1
        or isinstance(attempt_count, bool)
        or not isinstance(attempt_count, int)
        or attempt_number != attempt_count
    ):
        raise NestedEvidenceNamespaceError(
            "producer report terminal attempt identity is not result-bound"
        )
    return f"{session_id}:attempt:{attempt_number}"


def _producers(records: Sequence[_Record]) -> list[_Producer]:
    tasks = [
        record
        for record in records
        if isinstance(record.payload, dict)
        and record.payload.get("schema_version") == TASK_VERSION
    ]
    producers: list[_Producer] = []
    for result in records:
        if (
            not isinstance(result.payload, dict)
            or result.payload.get("schema_version") != RESULT_VERSION
        ):
            continue
        task_candidates = [
            (task, task_ref)
            for task in tasks
            if task.payload.get("task_id") == result.payload.get("task_id")
            if (task_ref := _task_result_ref(result, task)) is not None
        ]
        if not task_candidates:
            continue
        if len(task_candidates) != 1:
            raise NestedEvidenceNamespaceError(
                "producer result has ambiguous exact task inputs"
            )
        task, task_ref = task_candidates[0]
        report_ref = result.payload.get("report_ref")
        delta_ref = result.payload.get("actor_delta_ref")
        if not isinstance(report_ref, dict) or not isinstance(delta_ref, dict):
            continue
        report_matches = [
            record
            for record in records
            if record.digest == str(report_ref.get("artifact_digest", ""))
        ]
        delta_matches = [
            record
            for record in records
            if record.digest == str(delta_ref.get("artifact_digest", ""))
        ]
        # Historical reviewer packets legitimately forwarded only a result or
        # report.  Such a packet has no complete producer graph to optimize and
        # must retain the exact pre-namespace model-only route.
        if not report_matches or not delta_matches:
            continue
        if len(report_matches) != 1 or len(delta_matches) != 1:
            raise NestedEvidenceNamespaceError(
                "producer report or delta has ambiguous exact current inputs"
            )
        report = report_matches[0]
        delta = delta_matches[0]
        _validate_schema(task.payload, TASK_SCHEMA, label="producer task")
        _validate_schema(result.payload, RESULT_SCHEMA, label="producer result")
        _, task_raw = _verified_result_artifact(
            result,
            task_ref,
            label="producer task",
        )
        if task_raw != task.raw:
            raise NestedEvidenceNamespaceError(
                "producer task input is not its result-bound bytes"
            )
        report_path, report_raw = _verified_result_artifact(
            result,
            report_ref,
            label="producer report",
            expected_owner="abyss-stack",
        )
        _, delta_raw = _verified_result_artifact(
            result,
            delta_ref,
            label="producer delta",
            expected_owner="abyss-stack",
        )
        if report_raw != report.raw or delta_raw != delta.raw:
            raise NestedEvidenceNamespaceError(
                "producer report or delta input is not its result-bound bytes"
            )
        if (
            not isinstance(report.payload, dict)
            or report.payload.get("schema_version") != REPORT_VERSION
            or report.payload.get("task_id") != task.payload.get("task_id")
        ):
            raise NestedEvidenceNamespaceError("producer report identity is invalid")
        if (
            not isinstance(delta.payload, dict)
            or delta.payload.get("schema_version") != DELTA_VERSION
        ):
            raise NestedEvidenceNamespaceError("producer delta identity is invalid")
        _validate_schema(report.payload, REPORT_SCHEMA, label="producer report")
        _validate_schema(delta.payload, ACTOR_DELTA_SCHEMA, label="producer delta")
        final_manifest, final_raw, final_digest, projection = (
            _safe_result_final_manifest(result)
        )
        terminal_attempt_id = _terminal_attempt_id(result, report_path)
        if _sha256_bytes(_canonical_bytes(final_manifest)) != delta.payload.get(
            "final_manifest_digest"
        ):
            raise NestedEvidenceNamespaceError("producer delta does not bind its final manifest")
        change_digests = {
            str(change["after"]["sha256"])
            for change in delta.payload.get("changes", [])
            if isinstance(change, dict)
            and isinstance(change.get("after"), dict)
            and isinstance(change["after"].get("sha256"), str)
        }
        output_matches = {
            digest: [record for record in records if record.digest == digest]
            for digest in change_digests
        }
        if any(not matches for matches in output_matches.values()):
            continue
        if any(len(matches) != 1 for matches in output_matches.values()):
            raise NestedEvidenceNamespaceError(
                "producer outputs have ambiguous exact current inputs"
            )
        outputs = tuple(
            output_matches[digest][0] for digest in sorted(output_matches)
        )
        producers.append(
            _Producer(
                task=task,
                result=result,
                report=report,
                delta=delta,
                outputs=outputs,
                final_manifest=final_manifest,
                final_manifest_raw=final_raw,
                final_manifest_raw_digest=final_digest,
                workspace=projection,
                terminal_attempt_id=terminal_attempt_id,
            )
        )
    return sorted(
        producers,
        key=lambda producer: (
            producer.task_id,
            producer.result.digest,
            producer.result.input_id,
        ),
    )


def _json_pointer(parts: Iterable[str | int]) -> str:
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded)


def _iter_refs(
    value: Any,
    parts: tuple[str | int, ...] = (),
    field: str | None = None,
):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _iter_refs(child, (*parts, key), key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_refs(child, (*parts, index), field)
    elif isinstance(value, str) and field in {
        "evidence_ref",
        "evidence_refs",
        "source_ref",
        "source_refs",
    }:
        if value.startswith(("immutable:", "source:", "runtime:")):
            yield parts, value
        elif field in {"source_ref", "source_refs"} and "#" in value:
            yield parts, "source:" + value


def _split_ref(value: str, prefix: str) -> tuple[str, str]:
    identity, separator, anchor = value.removeprefix(prefix).partition("#")
    if not identity or not separator or not anchor or "#" in anchor:
        raise NestedEvidenceNamespaceError(f"invalid nested evidence ref: {value}")
    return identity, anchor


def _anchored_excerpt(raw: bytes, anchor: str, *, label: str) -> tuple[str, str]:
    match = LINE_ANCHOR_RE.fullmatch(anchor)
    if match is not None:
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        lines = raw.splitlines(keepends=True)
        if end < start or end > len(lines):
            raise NestedEvidenceNamespaceError(f"nested anchor is outside {label}")
        excerpt_raw = b"".join(lines[start - 1 : end])
    else:
        if (
            not anchor
            or len(anchor) > 256
            or any(ord(character) < 32 for character in anchor)
        ):
            raise NestedEvidenceNamespaceError(f"nested symbol anchor is invalid in {label}")
        excerpt_raw = anchor.encode("utf-8")
        if excerpt_raw not in raw:
            raise NestedEvidenceNamespaceError(f"nested symbol anchor is absent from {label}")
    try:
        excerpt = excerpt_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NestedEvidenceNamespaceError(f"nested anchored evidence is not UTF-8: {label}") from exc
    if len(excerpt_raw) > MAX_EXCERPT_BYTES:
        raise NestedEvidenceNamespaceError(f"nested anchored excerpt is too large: {label}")
    return excerpt, _sha256_bytes(excerpt_raw)


def _actor_envelope(record: _Record) -> dict[str, Any] | None:
    if (
        isinstance(record.payload, dict)
        and record.payload.get("schema_version") == ACTOR_INPUT_VERSION
    ):
        return record.payload
    return None


def _relative_is_allowed(relative: str, allowed: Sequence[str]) -> bool:
    if not relative or relative.startswith("/") or "\\" in relative or "\0" in relative:
        return False
    parts = tuple(relative.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        return False
    return any(
        candidate == "."
        or relative == candidate
        or relative.startswith(candidate + "/")
        for candidate in allowed
    )


def _secret_shaped_path(relative: str) -> bool:
    normalized = relative.replace("\\", "/").strip()
    if not normalized:
        return False
    parts = tuple(part.lower() for part in normalized.split("/") if part)
    if not parts:
        return False
    name = parts[-1]
    return (
        any(part in SECRET_PATH_PARTS for part in parts)
        or name in SECRET_FILE_NAMES
        or SECRET_FILE_TOKEN_RE.search(name) is not None
        or name.startswith(".env.")
        or name.endswith((".jks", ".kdbx", ".key", ".p12", ".pem"))
    )


def _manifest_entry(producer: _Producer, relative: str) -> dict[str, Any]:
    matches = [
        item
        for item in producer.final_manifest.get("content_entries", [])
        if isinstance(item, dict) and item.get("path") == relative
    ]
    if len(matches) != 1 or matches[0].get("kind") != "file":
        raise NestedEvidenceNamespaceError(
            f"producer manifest does not contain one regular source: {relative}"
        )
    return matches[0]


def _producer_file(producer: _Producer, relative: str) -> tuple[bytes, dict[str, Any]]:
    entry = _manifest_entry(producer, relative)
    review_seal = _producer_review_seal(producer.result)
    if review_seal is not None:
        seal_root, seal_metadata = review_seal
        seal_entries = [
            item
            for item in seal_metadata.get("tree_entries", [])
            if isinstance(item, dict)
            and item.get("path") == relative
            and item.get("kind") == "file"
        ]
        if len(seal_entries) != 1:
            raise NestedEvidenceNamespaceError(
                f"producer sealed source is not unique: {relative}"
            )
        object_digest = str(seal_entries[0].get("object_digest", ""))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", object_digest):
            raise NestedEvidenceNamespaceError(
                f"producer sealed source has no exact object: {relative}"
            )
        raw = _read_regular(seal_root / "objects" / object_digest.removeprefix("sha256:"))
        if (
            _sha256_bytes(raw) != object_digest
            or object_digest != entry.get("sha256")
        ):
            raise NestedEvidenceNamespaceError(
                f"producer sealed source bytes drifted: {relative}"
            )
        return raw, entry
    candidate = producer.workspace.joinpath(*relative.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(producer.workspace)
    except (OSError, ValueError) as exc:
        raise NestedEvidenceNamespaceError(
            f"producer source coordinate escaped: {relative}"
        ) from exc
    if resolved != candidate or candidate.is_symlink():
        raise NestedEvidenceNamespaceError(
            f"producer source coordinate is not exact: {relative}"
        )
    raw = _read_regular(candidate)
    if _sha256_bytes(raw) != entry.get("sha256"):
        raise NestedEvidenceNamespaceError(f"producer source bytes drifted: {relative}")
    return raw, entry


def _stable_entry_id(
    producer: _Producer,
    artifact: _Record,
    pointer: str,
    original_ref: str,
    target: str,
) -> str:
    raw = "\0".join(
        (producer.task.digest, artifact.digest, pointer, original_ref, target)
    ).encode("utf-8")
    return "nested-evidence-" + hashlib.sha256(raw).hexdigest()[:24]


def _resolve_immutable(
    producer: _Producer,
    records: Sequence[_Record],
    alias: str,
    anchor: str,
) -> tuple[dict[str, Any], bool]:
    task_inputs = [
        item
        for item in producer.task.payload.get("immutable_inputs", [])
        if isinstance(item, dict) and item.get("input_id") == alias
    ]
    if len(task_inputs) != 1 or not isinstance(task_inputs[0].get("provenance"), dict):
        raise NestedEvidenceNamespaceError(
            f"producer immutable alias is not uniquely bound: {alias}"
        )
    source_digest = str(task_inputs[0]["provenance"].get("artifact_digest", ""))
    candidates: list[_Record] = []
    for record in records:
        envelope = _actor_envelope(record)
        if (
            envelope is not None
            and envelope.get("input_id") == alias
            and envelope.get("source_artifact_digest") == source_digest
        ):
            candidates.append(record)
    if len(candidates) != 1:
        raise NestedEvidenceNamespaceError(
            f"producer immutable alias {alias} has {len(candidates)} exact upstream envelopes"
        )
    target = candidates[0]
    excerpt, excerpt_digest = _anchored_excerpt(
        target.raw,
        anchor,
        label=f"upstream immutable {alias}",
    )
    collision = any(
        record.input_id == alias and record.digest != target.digest for record in records
    )
    return (
        {
            "kind": "upstream-actor-envelope-exact",
            "producer_input_id": alias,
            "producer_source_artifact_digest": source_digest,
            "target_input_id": target.input_id,
            "target_envelope_digest": target.digest,
            "validated_anchor": anchor,
            "anchored_excerpt": excerpt,
            "anchored_excerpt_digest": excerpt_digest,
        },
        collision,
    )


def _resolve_source(producer: _Producer, relative: str, anchor: str) -> dict[str, Any]:
    allowed = [
        str(item)
        for item in producer.task.payload.get(
            "source_evidence_paths",
            producer.task.payload.get("allowed_paths", []),
        )
    ]
    if not _relative_is_allowed(relative, allowed) or _secret_shaped_path(relative):
        raise NestedEvidenceNamespaceError(
            f"producer source ref is outside its safe task scope: {relative}"
        )
    raw, manifest_entry = _producer_file(producer, relative)
    excerpt, excerpt_digest = _anchored_excerpt(
        raw,
        anchor,
        label=f"producer source {relative}",
    )
    return {
        "kind": "producer-final-workspace-source-exact",
        "source_path": relative,
        "source_artifact_digest": manifest_entry["sha256"],
        "producer_final_manifest_digest": producer.final_manifest_raw_digest,
        "validated_anchor": anchor,
        "anchored_excerpt": excerpt,
        "anchored_excerpt_digest": excerpt_digest,
    }


def _manifest_anchor_resolution(
    producer: _Producer,
    anchor: str,
    value: Any | None = None,
) -> dict[str, Any]:
    if LINE_ANCHOR_RE.fullmatch(anchor) is not None:
        excerpt, excerpt_digest = _anchored_excerpt(
            producer.final_manifest_raw,
            anchor,
            label="producer final manifest",
        )
    else:
        excerpt_raw = _canonical_bytes(value)
        if len(excerpt_raw) > MAX_EXCERPT_BYTES:
            raise NestedEvidenceNamespaceError(
                "nested final-manifest value exceeds its excerpt bound"
            )
        excerpt = excerpt_raw.decode("utf-8")
        excerpt_digest = _sha256_bytes(excerpt_raw)
    return {
        "kind": "producer-final-workspace-manifest-exact",
        "manifest_anchor": anchor,
        "producer_final_manifest_digest": producer.final_manifest_raw_digest,
        "manifest_value_digest": excerpt_digest,
        "anchored_excerpt": excerpt,
    }


def _select_validation_observation(
    result_payload: Mapping[str, Any],
    terminal_attempt_id: str,
    command_id: str,
) -> dict[str, Any]:
    observations = [
        item
        for item in result_payload.get("executed_commands", [])
        if isinstance(item, dict)
        and item.get("attempt_id") == terminal_attempt_id
        and item.get("validation_command_id") == command_id
        and item.get("status") == "completed"
        and item.get("exit_code") == 0
    ]
    if len(observations) != 1:
        raise NestedEvidenceNamespaceError(
            f"producer validation {command_id} has {len(observations)} exact "
            f"observations in terminal attempt {terminal_attempt_id}"
        )
    return observations[0]


def _resolve_runtime(
    producer: _Producer,
    records: Sequence[_Record],
    runtime_id: str,
    anchor: str,
) -> dict[str, Any]:
    if runtime_id.startswith("validation:"):
        if anchor:
            raise NestedEvidenceNamespaceError("nested validation ref carries an anchor")
        command_id = runtime_id.removeprefix("validation:")
        _select_validation_observation(
            producer.result.payload,
            producer.terminal_attempt_id,
            command_id,
        )
        return {
            "kind": "producer-validation-observation-exact",
            "validation_command_id": command_id,
            "producer_result_input_id": producer.result.input_id,
            "producer_attempt_id": producer.terminal_attempt_id,
            "observed_status": "passed",
        }
    if runtime_id != "workspace-final-manifest":
        raise NestedEvidenceNamespaceError(
            f"unsupported nested runtime evidence: {runtime_id}"
        )
    if LINE_ANCHOR_RE.fullmatch(anchor) is not None:
        return _manifest_anchor_resolution(producer, anchor)
    if anchor in producer.final_manifest:
        return _manifest_anchor_resolution(
            producer,
            anchor,
            {anchor: producer.final_manifest[anchor]},
        )
    manifest_entry = _manifest_entry(producer, anchor)
    digest = str(manifest_entry.get("sha256", ""))
    delta_edges = [
        change
        for change in producer.delta.payload.get("changes", [])
        if isinstance(change, dict)
        and change.get("path") == anchor
        and isinstance(change.get("after"), dict)
        and change["after"].get("sha256") == digest
    ]
    if not delta_edges:
        return _manifest_anchor_resolution(producer, anchor, manifest_entry)
    if len(delta_edges) != 1:
        raise NestedEvidenceNamespaceError(
            f"producer runtime output is not uniquely closed: {anchor}"
        )
    output_raw, _ = _producer_file(producer, anchor)
    targets = [record for record in records if record.digest == digest]
    if len(targets) != 1:
        raise NestedEvidenceNamespaceError(
            f"producer runtime output is not uniquely admitted: {anchor}"
        )
    if _sha256_bytes(output_raw) != targets[0].digest:
        raise NestedEvidenceNamespaceError(
            f"producer runtime output differs from its admitted review input: {anchor}"
        )
    return {
        "kind": "producer-final-workspace-output-exact",
        "output_path": anchor,
        "output_artifact_digest": digest,
        "target_input_id": targets[0].input_id,
        "producer_delta_input_id": producer.delta.input_id,
        "producer_final_manifest_digest": producer.final_manifest_raw_digest,
        "validated_anchor": anchor,
    }


def build_nested_evidence_namespace(
    *,
    review_task_id: str,
    review_task_digest: str,
    immutable_inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Return a closed namespace, or ``None`` when no producer graph is present."""

    records = _records(immutable_inputs)
    producers = _producers(records)
    if not producers:
        return None
    totals = {
        "producer_count": 0,
        "artifact_count": 0,
        "reference_occurrences": 0,
        "immutable_exact": 0,
        "source_exact": 0,
        "runtime_exact": 0,
        "validation_exact": 0,
        "same_name_digest_collisions": 0,
        "unresolved": 0,
    }
    producer_receipts: list[dict[str, Any]] = []
    for producer in producers:
        entries: list[dict[str, Any]] = []
        for artifact in sorted(
            (producer.report, *producer.outputs),
            key=lambda item: item.input_id,
        ):
            if not isinstance(artifact.payload, (dict, list)):
                continue
            artifact_had_ref = False
            for parts, original_ref in _iter_refs(artifact.payload):
                artifact_had_ref = True
                pointer = _json_pointer(parts)
                if original_ref.startswith("immutable:"):
                    alias, anchor = _split_ref(original_ref, "immutable:")
                    resolution, collision = _resolve_immutable(
                        producer,
                        records,
                        alias,
                        anchor,
                    )
                    totals["immutable_exact"] += 1
                    if collision:
                        totals["same_name_digest_collisions"] += 1
                elif original_ref.startswith("source:"):
                    relative, anchor = _split_ref(original_ref, "source:")
                    resolution = _resolve_source(producer, relative, anchor)
                    collision = False
                    totals["source_exact"] += 1
                elif original_ref.startswith("runtime:validation:"):
                    resolution = _resolve_runtime(
                        producer,
                        records,
                        original_ref.removeprefix("runtime:"),
                        "",
                    )
                    collision = False
                    totals["validation_exact"] += 1
                elif original_ref.startswith("runtime:"):
                    runtime_id, anchor = _split_ref(original_ref, "runtime:")
                    resolution = _resolve_runtime(
                        producer,
                        records,
                        runtime_id,
                        anchor,
                    )
                    collision = False
                    totals["runtime_exact"] += 1
                else:
                    raise NestedEvidenceNamespaceError(
                        f"unsupported nested evidence ref: {original_ref}"
                    )
                target = str(
                    resolution.get("target_input_id")
                    or resolution.get("source_artifact_digest")
                    or resolution.get("validation_command_id")
                    or resolution.get("output_artifact_digest")
                    or resolution.get("manifest_value_digest")
                )
                entries.append(
                    {
                        "entry_id": _stable_entry_id(
                            producer,
                            artifact,
                            pointer,
                            original_ref,
                            target,
                        ),
                        "artifact_input_id": artifact.input_id,
                        "artifact_digest": artifact.digest,
                        "json_pointer": pointer,
                        "original_ref": original_ref,
                        "same_name_digest_collision": collision,
                        "resolution": resolution,
                    }
                )
                totals["reference_occurrences"] += 1
            if artifact_had_ref:
                totals["artifact_count"] += 1
        producer_receipts.append(
            {
                "producer_task_id": producer.task_id,
                "task_input_id": producer.task.input_id,
                "task_digest": producer.task.digest,
                "result_input_id": producer.result.input_id,
                "result_digest": producer.result.digest,
                "report_input_id": producer.report.input_id,
                "report_digest": producer.report.digest,
                "delta_input_id": producer.delta.input_id,
                "delta_digest": producer.delta.digest,
                "entries": sorted(entries, key=lambda item: item["entry_id"]),
            }
        )
        totals["producer_count"] += 1
    if totals["reference_occurrences"] == 0:
        return None
    namespace: dict[str, Any] = {
        "schema_version": NAMESPACE_VERSION,
        "review_task_id": review_task_id,
        "review_task_digest": review_task_digest,
        "status": "closed",
        "summary": totals,
        "producers": producer_receipts,
    }
    namespace["namespace_digest"] = nested_evidence_namespace_digest(namespace)
    if len(_canonical_bytes(namespace)) > MAX_NAMESPACE_BYTES:
        raise NestedEvidenceNamespaceError(
            "nested evidence namespace exceeds its bounded artifact limit"
        )
    return namespace
