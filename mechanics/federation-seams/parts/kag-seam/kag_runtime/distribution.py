from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .bundle import write_json_atomic


OWNER_RELEASE_SCHEMA = "aoa-kag-owner-family-release-v1"
PORTABLE_BUNDLE_SCHEMA = "aoa-kag-portable-family-bundle-v1"
CORPUS_SCHEMA = "aoa-repo-local-kag-corpus-manifest-v1"
DISTRIBUTION_SCHEMA = "aoa-repo-local-kag-distribution-manifest-v1"
PACK_INDEX_SCHEMA = "aoa-kag-pack-index-v1"
HOT_PROFILE_SCHEMA = "aoa-repo-local-kag-hot-profile-v1"
LOCATOR_SCHEMA = "aoa-kag-artifact-locator-v1"
COMPOSITION_SCHEMA = "aoa-kag-os-composition-v1"
TRUST_GATE_SCHEMA = "abyss_machine_artifact_trust_gate_v1"
OWNER_STATE_SCHEMA = "abyss-stack-kag-tiered-owner-state-v1"
CURRENT_STATE_SCHEMA = "abyss-stack-kag-tiered-distribution-current-v1"
COMPOSITION_STATE_SCHEMA = "abyss-stack-kag-tiered-composition-state-v1"
MATERIALIZATION_RECEIPT_SCHEMA = (
    "abyss-stack-kag-tiered-materialization-receipt-v1"
)
ROLLBACK_RECEIPT_SCHEMA = "abyss-stack-kag-tiered-rollback-receipt-v1"

OWNER_RELEASE_ARTIFACT_CLASS = "kag_owner_family_release"
COMPOSITION_ARTIFACT_CLASS = "kag_os_composition"
PUBLIC_ACCESS_POLICY = "public-kag"
ZERO_DIGEST = "sha256:" + ("0" * 64)
OS_OWNER_COUNT = 24
OS_GIT_HOT_TARGET_BYTES = 234_881_024
ADMITTED_LIFECYCLES = {"manually-verified", "release-ready", "published"}
DELIVERY_STATES = {
    "complete",
    "git_hot_complete",
    "hot_only",
    "artifact_required",
    "artifact_unavailable",
    "rebuild_available",
    "rebuild_required",
    "stale",
    "digest_mismatch",
    "revoked",
    "access_denied",
}
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^commit:[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class DistributionError(RuntimeError):
    def __init__(self, state: str, message: str) -> None:
        if state not in DELIVERY_STATES:
            raise ValueError(f"unsupported KAG delivery state: {state}")
        self.state = state
        super().__init__(message)


@dataclass(frozen=True)
class TrustedOwnerFamily:
    root: Path
    owner: str
    source_ref: str
    source_snapshot: str
    release_digest: str
    corpus_digest: str
    distribution_digest: str
    release: Mapping[str, Any]
    corpus: Mapping[str, Any]
    distribution: Mapping[str, Any]
    hot_profile: Mapping[str, Any]
    locator_manifest: Mapping[str, Any]
    pack_index: Mapping[str, Any]
    bundle: Mapping[str, Any]
    objects: tuple[Mapping[str, Any], ...]
    packs: Mapping[str, Mapping[str, Any]]
    trust: Mapping[str, Any]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_uri(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _identity_digest(
    payload: Mapping[str, Any],
    identity_field: str,
    *,
    excluded_fields: Sequence[str] = (),
) -> str:
    candidate = copy.deepcopy(dict(payload))
    identity = candidate.get(identity_field)
    if not isinstance(identity, dict):
        raise DistributionError(
            "digest_mismatch", f"missing identity object: {identity_field}"
        )
    identity["content_digest"] = ZERO_DIGEST
    for field in excluded_fields:
        candidate.pop(field, None)
    return _sha256_uri(_canonical_bytes(candidate))


def _composition_digest(payload: Mapping[str, Any]) -> str:
    return _identity_digest(
        payload,
        "composition_identity",
        excluded_fields=("signature",),
    )


def _corpus_digest(payload: Mapping[str, Any]) -> str:
    identity = _mapping(payload.get("corpus_identity"), "corpus identity")
    material = {
        "owner": payload.get("repo"),
        "source_snapshot": identity.get("source_snapshot"),
        "epochs": payload.get("epochs"),
        "partitioning": payload.get("partitioning"),
        "normalization": payload.get("normalization"),
        "source_index_header": payload.get("source_index_header"),
        "compatibility": payload.get("compatibility"),
        "objects": payload.get("objects"),
    }
    return _sha256_uri(_canonical_bytes(material))


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DistributionError(
            "artifact_unavailable", f"{label} is missing: {path.name}"
        ) from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DistributionError(
            "digest_mismatch", f"{label} is not valid JSON: {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise DistributionError(
            "digest_mismatch", f"{label} must be a JSON object"
        )
    return payload


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DistributionError("digest_mismatch", f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise DistributionError(
            "digest_mismatch", f"{label} must be an array of objects"
        )
    return list(value)


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise DistributionError(
            "digest_mismatch", f"{label} must be sha256:<64 lowercase hex>"
        )
    return value


def _safe_relative(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise DistributionError("digest_mismatch", f"{label} is missing")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise DistributionError(
            "access_denied", f"{label} must be a safe relative path"
        )
    return Path(*pure.parts)


def _safe_owner(value: Any) -> str:
    if not isinstance(value, str) or _OWNER_RE.fullmatch(value) is None:
        raise DistributionError("access_denied", "owner is not path-safe")
    return value


def _object_key(digest: str) -> str:
    value = _digest(digest, "object digest").removeprefix("sha256:")
    return f"objects/sha256/{value[:2]}/{value}"


def _pack_key(digest: str) -> str:
    value = _digest(digest, "pack digest").removeprefix("sha256:")
    return f"packs/sha256/{value[:2]}/{value}.pack"


def _rooted(root: Path, relative: Path, label: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DistributionError("access_denied", f"{label} escapes its root") from exc
    return candidate


def _slim_trust(
    gate: Mapping[str, Any],
    *,
    artifact_class: str,
    content_digest: str,
    source_repo: str,
    source_ref: str = "",
) -> dict[str, Any]:
    if gate.get("schema") != TRUST_GATE_SCHEMA:
        raise DistributionError("access_denied", "trust-gate schema is unsupported")
    if gate.get("ok") is not True or gate.get("verdict") not in {"allow", "warn"}:
        blockers = ",".join(str(item) for item in gate.get("blockers", []))
        raise DistributionError(
            "access_denied",
            "abyss-machine trust-gate denied the artifact"
            + (f": {blockers}" if blockers else ""),
        )
    if gate.get("artifact_class") != artifact_class:
        raise DistributionError("access_denied", "trust-gate artifact class mismatch")
    record = _mapping(gate.get("record"), "trust-gate record")
    if record.get("artifact_class") != artifact_class:
        raise DistributionError("access_denied", "registry artifact class mismatch")
    if record.get("source_repo") != source_repo:
        raise DistributionError("access_denied", "registry source owner mismatch")
    if source_ref and record.get("source_ref") != source_ref:
        raise DistributionError("access_denied", "registry source ref mismatch")
    if record.get("access_policy") != PUBLIC_ACCESS_POLICY:
        raise DistributionError("access_denied", "registry access policy mismatch")
    if (
        record.get("terminal_state") is True
        or record.get("lifecycle_state") not in ADMITTED_LIFECYCLES
    ):
        state = (
            "revoked"
            if record.get("lifecycle_state") == "revoked"
            else "access_denied"
        )
        raise DistributionError(state, "registry lifecycle is not consumable")
    external = _mapping(
        record.get("external_artifact_identity"),
        "registry external artifact identity",
    )
    if external.get("content_digest") != content_digest:
        raise DistributionError(
            "digest_mismatch", "registry content identity does not match payload"
        )
    claims = _mapping(gate.get("inspected_claims"), "trust-gate inspected claims")
    subject_store = _mapping(
        claims.get("artifact_subject_store"),
        "trust-gate artifact subject store",
    )
    if subject_store.get("ok") is not True:
        raise DistributionError(
            "artifact_unavailable", "verified artifact subject store is unavailable"
        )
    return {
        "gate_schema": TRUST_GATE_SCHEMA,
        "verdict": gate.get("verdict"),
        "record_id": gate.get("record_id"),
        "subject_digest": gate.get("subject_digest"),
        "consumer_intent": gate.get("consumer_intent"),
        "lifecycle_state": record.get("lifecycle_state"),
        "trust_root_mode": record.get("trust_root_mode"),
        "access_policy": record.get("access_policy"),
        "subject_store": {
            "ok": True,
            "path": subject_store.get("path"),
            "aggregate_digest": subject_store.get("aggregate_digest"),
        },
    }


def _require_subject_store_root(root: Path, trust: Mapping[str, Any]) -> None:
    store = _mapping(trust.get("subject_store"), "trusted subject store")
    raw_path = store.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise DistributionError(
            "artifact_unavailable", "trust-gate omitted the subject-store path"
        )
    if Path(raw_path).expanduser().resolve() != root:
        raise DistributionError(
            "access_denied",
            "family root is not the subject store admitted by abyss-machine",
        )


def _descriptor_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        item.get(field)
        for field in ("kind", "range", "content_digest", "bytes", "records")
    )


def load_trusted_owner_family(
    family_root: str | Path,
    trust_gate_path: str | Path,
    *,
    expected_owner: str = "",
) -> TrustedOwnerFamily:
    root = Path(family_root).expanduser().resolve()
    release = _read_json(root / "owner-family-release.json", "owner release")
    bundle = _read_json(root / "bundle.manifest.json", "portable bundle")
    corpus = _read_json(
        root / "kag" / "indexes" / "corpus.manifest.json",
        "corpus manifest",
    )
    distribution = _read_json(
        root / "kag" / "indexes" / "index_family.manifest.json",
        "distribution manifest",
    )
    hot_profile = _read_json(
        root / "kag" / "indexes" / "hot_profile.json",
        "hot profile",
    )
    locator_manifest = _read_json(
        root / "kag" / "indexes" / "artifact_locators.json",
        "artifact locator manifest",
    )
    pack_index = _read_json(root / "pack-index.json", "pack index")

    if release.get("schema_version") != OWNER_RELEASE_SCHEMA:
        raise DistributionError("digest_mismatch", "owner release schema mismatch")
    if bundle.get("schema_version") != PORTABLE_BUNDLE_SCHEMA:
        raise DistributionError("digest_mismatch", "portable bundle schema mismatch")
    if corpus.get("schema_version") != CORPUS_SCHEMA:
        raise DistributionError("digest_mismatch", "corpus manifest schema mismatch")
    if distribution.get("schema_version") != DISTRIBUTION_SCHEMA:
        raise DistributionError(
            "digest_mismatch", "distribution manifest schema mismatch"
        )
    if hot_profile.get("schema_version") != HOT_PROFILE_SCHEMA:
        raise DistributionError("digest_mismatch", "hot profile schema mismatch")
    if locator_manifest.get("schema_version") != LOCATOR_SCHEMA:
        raise DistributionError(
            "digest_mismatch", "artifact locator schema mismatch"
        )
    if pack_index.get("schema_version") != PACK_INDEX_SCHEMA:
        raise DistributionError("digest_mismatch", "pack index schema mismatch")

    release_identity = _mapping(
        release.get("release_identity"), "release identity"
    )
    if (
        release_identity.get("artifact_class") != OWNER_RELEASE_ARTIFACT_CLASS
        or release_identity.get("abi_epoch") != OWNER_RELEASE_SCHEMA
    ):
        raise DistributionError("access_denied", "owner release ABI mismatch")
    release_digest = _digest(
        release_identity.get("content_digest"), "release content digest"
    )
    if release_digest != _identity_digest(
        release, "release_identity", excluded_fields=("signature",)
    ):
        raise DistributionError("digest_mismatch", "owner release digest mismatch")

    repo = _mapping(release.get("repo"), "owner release repo")
    source = _mapping(release.get("source"), "owner release source")
    owner = _safe_owner(repo.get("name"))
    if expected_owner and owner != expected_owner:
        raise DistributionError("access_denied", "unexpected owner family")
    if source.get("owner") != owner:
        raise DistributionError("access_denied", "release source owner mismatch")
    source_ref = str(source.get("ref") or "")
    if (
        _COMMIT_RE.fullmatch(source_ref) is None
        or repo.get("git_ref") != source_ref
    ):
        raise DistributionError(
            "access_denied", "release is not bound to one exact owner commit"
        )
    source_snapshot = _digest(source.get("snapshot"), "source snapshot")

    lifecycle = _mapping(release.get("lifecycle"), "release lifecycle")
    if lifecycle.get("state") == "revoked" or lifecycle.get("revoked") is True:
        raise DistributionError("revoked", "owner family release is revoked")
    if lifecycle.get("state") not in ADMITTED_LIFECYCLES:
        raise DistributionError(
            "access_denied", "owner family lifecycle is not admitted"
        )
    signature = _mapping(release.get("signature"), "release signature")
    if (
        signature.get("verification_state") != "verified"
        or signature.get("subject_digest") != release_digest
    ):
        raise DistributionError(
            "access_denied", "owner family signature is not verified"
        )
    provenance = _mapping(release.get("provenance"), "release provenance")
    if not str(provenance.get("verification_receipt") or ""):
        raise DistributionError(
            "access_denied", "owner family verification receipt is missing"
        )

    corpus_identity = _mapping(corpus.get("corpus_identity"), "corpus identity")
    distribution_identity = _mapping(
        distribution.get("distribution_identity"), "distribution identity"
    )
    corpus_digest = _digest(
        corpus_identity.get("content_digest"), "corpus digest"
    )
    distribution_digest = _digest(
        distribution_identity.get("content_digest"), "distribution digest"
    )
    hot_identity = _mapping(
        hot_profile.get("profile_identity"), "hot profile identity"
    )
    locator_identity = _mapping(
        locator_manifest.get("locator_identity"), "locator identity"
    )
    pack_identity = _mapping(
        pack_index.get("pack_index_identity"), "pack-index identity"
    )
    hot_digest = _digest(
        hot_identity.get("content_digest"), "hot profile digest"
    )
    locator_digest = _digest(
        locator_identity.get("content_digest"), "locator digest"
    )
    pack_index_digest = _digest(
        pack_identity.get("content_digest"), "pack-index digest"
    )
    if corpus_digest != _corpus_digest(corpus):
        raise DistributionError("digest_mismatch", "corpus identity digest mismatch")
    if distribution_digest != _identity_digest(
        distribution, "distribution_identity"
    ):
        raise DistributionError(
            "digest_mismatch", "distribution identity digest mismatch"
        )
    if hot_digest != _identity_digest(hot_profile, "profile_identity"):
        raise DistributionError(
            "digest_mismatch", "hot profile identity digest mismatch"
        )
    if locator_digest != _identity_digest(
        locator_manifest, "locator_identity"
    ):
        raise DistributionError(
            "digest_mismatch", "artifact locator identity digest mismatch"
        )
    if pack_index_digest != _identity_digest(
        pack_index, "pack_index_identity"
    ):
        raise DistributionError(
            "digest_mismatch", "pack-index identity digest mismatch"
        )
    if (
        release_identity.get("corpus_digest") != corpus_digest
        or release_identity.get("distribution_digest") != distribution_digest
    ):
        raise DistributionError(
            "digest_mismatch", "release does not bind corpus and distribution"
        )
    release_manifests = _mapping(
        release.get("manifests"), "release manifest identities"
    )
    expected_manifest_digests = {
        "corpus_digest": corpus_digest,
        "distribution_digest": distribution_digest,
        "hot_profile_digest": hot_digest,
        "locator_digest": locator_digest,
        "pack_index_digest": pack_index_digest,
    }
    for field, expected in expected_manifest_digests.items():
        if release_manifests.get(field) != expected:
            raise DistributionError(
                "digest_mismatch", f"owner release {field} mismatch"
            )
    if (
        distribution_identity.get("corpus_digest") != corpus_digest
        or hot_identity.get("corpus_digest") != corpus_digest
        or locator_identity.get("corpus_digest") != corpus_digest
        or pack_identity.get("corpus_digest") != corpus_digest
        or _mapping(
            distribution.get("corpus_manifest"),
            "distribution corpus manifest",
        ).get("content_digest")
        != corpus_digest
        or _mapping(
            distribution.get("hot_profile"),
            "distribution hot profile",
        ).get("content_digest")
        != hot_digest
        or _mapping(
            distribution.get("artifact_locators"),
            "distribution artifact locators",
        ).get("content_digest")
        != locator_digest
        or _mapping(
            distribution.get("transport"),
            "distribution transport",
        ).get("pack_index_digest")
        != pack_index_digest
    ):
        raise DistributionError(
            "digest_mismatch", "inner KAG manifest identities are not coherent"
        )
    for label, payload in (
        ("corpus", corpus),
        ("distribution", distribution),
        ("hot profile", hot_profile),
        ("artifact locators", locator_manifest),
        ("pack index", pack_index),
    ):
        payload_repo = _mapping(payload.get("repo"), f"{label} repo")
        if payload_repo.get("name") != owner:
            raise DistributionError(
                "access_denied", f"{label} owner does not match release"
            )

    bundle_identity = _mapping(bundle.get("bundle_identity"), "bundle identity")
    if bundle_identity.get("content_digest") != _identity_digest(
        bundle, "bundle_identity"
    ):
        raise DistributionError("digest_mismatch", "portable bundle digest mismatch")
    expected_bundle_fields = {
        "corpus_digest": corpus_digest,
        "distribution_digest": distribution_digest,
        "release_digest": release_digest,
    }
    for field, expected in expected_bundle_fields.items():
        if bundle_identity.get(field) != expected:
            raise DistributionError(
                "digest_mismatch", f"portable bundle {field} mismatch"
            )
    if bundle.get("network_required") is not False:
        raise DistributionError(
            "artifact_unavailable", "owner bundle is not offline-complete"
        )

    objects = _sequence(release.get("objects"), "release objects")
    corpus_objects = _sequence(corpus.get("objects"), "corpus objects")
    if sorted(_descriptor_key(item) for item in objects) != sorted(
        _descriptor_key(item) for item in corpus_objects
    ):
        raise DistributionError(
            "digest_mismatch", "release and corpus object sets differ"
        )
    hot_kinds = set(
        str(item)
        for item in _mapping(
            hot_profile.get("selection"), "hot profile selection"
        ).get("include_record_kinds", [])
    )
    seen_digests: set[str] = set()
    normalized_objects: list[Mapping[str, Any]] = []
    for item in objects:
        digest = _digest(item.get("content_digest"), "object content digest")
        if digest in seen_digests:
            raise DistributionError("digest_mismatch", "duplicate object digest")
        seen_digests.add(digest)
        if item.get("object_key") != _object_key(digest):
            raise DistributionError("digest_mismatch", "object CAS key mismatch")
        if (
            not isinstance(item.get("bytes"), int)
            or item["bytes"] <= 0
            or not isinstance(item.get("records"), int)
            or item["records"] <= 0
        ):
            raise DistributionError("digest_mismatch", "invalid object measurement")
        expected_placement = (
            "git_hot" if item.get("kind") in hot_kinds else "artifact_cold"
        )
        if item.get("placement") != expected_placement:
            raise DistributionError("digest_mismatch", "hot/cold placement mismatch")
        _safe_relative(item.get("object_key"), "object key")
        normalized_objects.append(item)

    release_packs = _sequence(release.get("packs"), "release packs")
    pack_index_packs = _sequence(pack_index.get("packs"), "pack-index packs")
    if release_packs != pack_index_packs:
        raise DistributionError("digest_mismatch", "release pack set mismatch")
    packs: dict[str, Mapping[str, Any]] = {}
    for item in release_packs:
        digest = _digest(item.get("pack_digest"), "pack digest")
        if item.get("object_key") != _pack_key(digest):
            raise DistributionError("digest_mismatch", "pack CAS key mismatch")
        _safe_relative(item.get("object_key"), "pack key")
        packs[digest] = item
    entries = _sequence(pack_index.get("entries"), "pack-index entries")
    entries_by_object: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        object_digest = _digest(
            entry.get("object_digest"), "pack-index object digest"
        )
        if object_digest in entries_by_object:
            raise DistributionError(
                "digest_mismatch", "duplicate pack-index object entry"
            )
        entries_by_object[object_digest] = entry
    for item in normalized_objects:
        declared = item.get("pack")
        indexed = entries_by_object.get(str(item["content_digest"]))
        if declared is None and indexed is None:
            continue
        if not isinstance(declared, Mapping) or indexed is None:
            raise DistributionError(
                "digest_mismatch", "owner object and pack index disagree"
            )
        if any(
            declared.get(field) != indexed.get(field)
            for field in ("pack_digest", "offset", "length")
        ):
            raise DistributionError(
                "digest_mismatch", "owner object pack range does not match index"
            )

    gate = _read_json(
        Path(trust_gate_path).expanduser().resolve(), "abyss-machine trust gate"
    )
    trust = _slim_trust(
        gate,
        artifact_class=OWNER_RELEASE_ARTIFACT_CLASS,
        content_digest=release_digest,
        source_repo=owner,
        source_ref=source_ref,
    )
    _require_subject_store_root(root, trust)
    return TrustedOwnerFamily(
        root=root,
        owner=owner,
        source_ref=source_ref,
        source_snapshot=source_snapshot,
        release_digest=release_digest,
        corpus_digest=corpus_digest,
        distribution_digest=distribution_digest,
        release=release,
        corpus=corpus,
        distribution=distribution,
        hot_profile=hot_profile,
        locator_manifest=locator_manifest,
        pack_index=pack_index,
        bundle=bundle,
        objects=tuple(normalized_objects),
        packs=packs,
        trust=trust,
    )


def _selected(
    item: Mapping[str, Any],
    *,
    kinds: set[str],
    range_prefixes: tuple[str, ...],
) -> bool:
    if kinds and item.get("kind") not in kinds:
        return False
    value = str(item.get("range") or "")
    return not range_prefixes or any(value.startswith(prefix) for prefix in range_prefixes)


def _object_bytes(family: TrustedOwnerFamily, item: Mapping[str, Any]) -> bytes:
    relative = _safe_relative(item.get("object_key"), "object key")
    direct = _rooted(family.root, relative, "object key")
    expected_digest = str(item["content_digest"])
    expected_bytes = int(item["bytes"])
    if direct.is_file():
        content = direct.read_bytes()
        if len(content) != expected_bytes or _sha256_uri(content) != expected_digest:
            raise DistributionError(
                "digest_mismatch", f"corrupted owner object: {expected_digest}"
            )
        return content
    pack = item.get("pack")
    if not isinstance(pack, Mapping):
        raise DistributionError(
            "artifact_unavailable", f"owner object is unavailable: {expected_digest}"
        )
    pack_digest = _digest(pack.get("pack_digest"), "object pack digest")
    descriptor = family.packs.get(pack_digest)
    if descriptor is None:
        raise DistributionError("digest_mismatch", "object names an unknown pack")
    pack_path = _rooted(
        family.root,
        _safe_relative(descriptor.get("object_key"), "pack key"),
        "pack key",
    )
    try:
        pack_content = pack_path.read_bytes()
    except FileNotFoundError as exc:
        raise DistributionError(
            "artifact_unavailable", f"transport pack is unavailable: {pack_digest}"
        ) from exc
    if (
        len(pack_content) != descriptor.get("bytes")
        or _sha256_uri(pack_content) != pack_digest
    ):
        raise DistributionError(
            "digest_mismatch", f"corrupted transport pack: {pack_digest}"
        )
    offset = pack.get("offset")
    length = pack.get("length")
    if (
        not isinstance(offset, int)
        or not isinstance(length, int)
        or offset < 0
        or length != expected_bytes
        or offset + length > len(pack_content)
    ):
        raise DistributionError("digest_mismatch", "invalid pack byte range")
    content = pack_content[offset : offset + length]
    if _sha256_uri(content) != expected_digest:
        raise DistributionError(
            "digest_mismatch", "pack extraction did not reproduce the object"
        )
    return content


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _owner_root(runtime_root: Path, owner: str) -> Path:
    return runtime_root / "distribution" / "owners" / _safe_owner(owner)


def _read_optional(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _state_objects_present(runtime_root: Path, state: Mapping[str, Any]) -> bool:
    objects = state.get("objects")
    if not isinstance(objects, list):
        return False
    for item in objects:
        if not isinstance(item, Mapping):
            return False
        try:
            relative = _safe_relative(item.get("object_key"), "state object key")
            expected = _digest(item.get("content_digest"), "state object digest")
        except DistributionError:
            return False
        path = _rooted(runtime_root / "cas", relative, "state object key")
        if not path.is_file() or _sha256_uri(path.read_bytes()) != expected:
            return False
    return True


def _refresh_current(runtime_root: Path) -> dict[str, Any]:
    owners_root = runtime_root / "distribution" / "owners"
    active: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    if owners_root.is_dir():
        for owner_root in sorted(path for path in owners_root.iterdir() if path.is_dir()):
            current = _read_optional(owner_root / "current.json")
            candidate = _read_optional(owner_root / "candidate.json")
            if current:
                active.append(current)
            if candidate:
                candidates.append(candidate)
    composition = _read_optional(
        runtime_root / "distribution" / "composition" / "current.json"
    )
    composition_active = (
        composition.get("schema_version") == COMPOSITION_STATE_SCHEMA
        and composition.get("owner_count") == OS_OWNER_COUNT
    )
    if composition_active:
        state = "complete"
    elif candidates:
        states = {str(item.get("delivery_state") or "") for item in candidates}
        state = "artifact_required" if "artifact_required" in states else "hot_only"
    elif active:
        state = "rebuild_required"
    else:
        state = "rebuild_available"
    payload = {
        "schema_version": CURRENT_STATE_SCHEMA,
        "updated_at": _now(),
        "state": state,
        "composition_identity": composition.get("composition_identity"),
        "owners": [
            {
                "owner": item.get("owner"),
                "source_ref": item.get("source_ref"),
                "release_digest": item.get("release_digest"),
                "corpus_digest": item.get("corpus_digest"),
                "distribution_digest": item.get("distribution_digest"),
                "delivery_state": item.get("delivery_state"),
                "projection_impact": item.get("projection_impact"),
            }
            for item in active
        ],
        "candidates": [
            {
                "owner": item.get("owner"),
                "release_digest": item.get("release_digest"),
                "delivery_state": item.get("delivery_state"),
            }
            for item in candidates
        ],
        "summary": {
            "active_owner_count": len(active),
            "candidate_owner_count": len(candidates),
            "composition_active": composition_active,
        },
        "degradation": (
            []
            if state == "complete"
            else [
                {
                    "target": "tiered-distribution",
                    "state": state,
                    "fallback": "last-good-projection-or-git-hot",
                }
            ]
        ),
    }
    write_json_atomic(runtime_root / "distribution" / "current.json", payload)
    return payload


def materialize_owner_family(
    family: TrustedOwnerFamily,
    runtime_root: str | Path,
    *,
    kinds: Sequence[str] = (),
    range_prefixes: Sequence[str] = (),
) -> dict[str, Any]:
    root = Path(runtime_root).expanduser().resolve()
    selected_kinds = {str(item) for item in kinds if str(item)}
    prefixes = tuple(dict.fromkeys(str(item) for item in range_prefixes if str(item)))
    selected = [
        item
        for item in family.objects
        if _selected(item, kinds=selected_kinds, range_prefixes=prefixes)
    ]
    if not selected:
        raise DistributionError(
            "artifact_required", "selection matched no owner-family objects"
        )
    started = time.monotonic()
    added_objects = 0
    reused_objects = 0
    added_bytes = 0
    reused_bytes = 0
    cas_root = root / "cas"
    for item in selected:
        relative = _safe_relative(item.get("object_key"), "object key")
        target = _rooted(cas_root, relative, "object key")
        expected_digest = str(item["content_digest"])
        if target.is_file():
            content = target.read_bytes()
            if (
                len(content) != item["bytes"]
                or _sha256_uri(content) != expected_digest
            ):
                raise DistributionError(
                    "digest_mismatch",
                    f"local CAS object is corrupted: {expected_digest}",
                )
            reused_objects += 1
            reused_bytes += len(content)
            continue
        content = _object_bytes(family, item)
        _write_bytes_atomic(target, content)
        added_objects += 1
        added_bytes += len(content)

    available = 0
    for item in family.objects:
        target = _rooted(
            cas_root,
            _safe_relative(item.get("object_key"), "object key"),
            "object key",
        )
        if (
            target.is_file()
            and target.stat().st_size == item["bytes"]
            and _sha256_uri(target.read_bytes()) == item["content_digest"]
        ):
            available += 1
    complete = available == len(family.objects)
    selected_hot_only = all(item.get("placement") == "git_hot" for item in selected)
    delivery_state = (
        "complete"
        if complete
        else ("hot_only" if selected_hot_only else "artifact_required")
    )

    owner_root = _owner_root(root, family.owner)
    previous = _read_optional(owner_root / "current.json")
    previous_corpus = str(previous.get("corpus_digest") or "")
    if previous_corpus == family.corpus_digest:
        projection_impact = {
            "class": "none",
            "affected_owners": [],
            "cross_owner_relations": "unchanged",
        }
    else:
        projection_impact = {
            "class": "owner_only",
            "affected_owners": [family.owner],
            "cross_owner_relations": "bounded_recompute_required",
        }
    state_objects = [
        {
            "kind": item.get("kind"),
            "range": item.get("range"),
            "content_digest": item.get("content_digest"),
            "bytes": item.get("bytes"),
            "placement": item.get("placement"),
            "object_key": item.get("object_key"),
        }
        for item in family.objects
    ]
    state = {
        "schema_version": OWNER_STATE_SCHEMA,
        "owner": family.owner,
        "source_ref": family.source_ref,
        "source_snapshot": family.source_snapshot,
        "release_digest": family.release_digest,
        "corpus_digest": family.corpus_digest,
        "distribution_digest": family.distribution_digest,
        "delivery_state": delivery_state,
        "materialized_at": _now(),
        "selection": {
            "kinds": sorted(selected_kinds),
            "range_prefixes": list(prefixes),
            "selected_objects": len(selected),
            "total_objects": len(family.objects),
        },
        "cache": {
            "objects_available": available,
            "objects_added": added_objects,
            "objects_reused": reused_objects,
            "bytes_added": added_bytes,
            "bytes_reused": reused_bytes,
            "hydration_latency_seconds": round(time.monotonic() - started, 6),
            "network_fetch_bytes": 0,
        },
        "trust": dict(family.trust),
        "projection_impact": projection_impact,
        "objects": state_objects,
        "canonical_truth": False,
        "owner_return": {
            "owner": family.owner,
            "source_ref": family.source_ref,
            "source_snapshot": family.source_snapshot,
        },
    }
    receipt_root = owner_root / "receipts"
    receipt_path = receipt_root / (
        family.release_digest.removeprefix("sha256:") + ".json"
    )
    receipt = {
        "schema_version": MATERIALIZATION_RECEIPT_SCHEMA,
        **state,
    }
    write_json_atomic(receipt_path, receipt)
    if complete:
        current_path = owner_root / "current.json"
        if previous and previous.get("release_digest") != family.release_digest:
            write_json_atomic(owner_root / "last-good.json", previous)
        write_json_atomic(current_path, state)
        (owner_root / "candidate.json").unlink(missing_ok=True)
    else:
        write_json_atomic(owner_root / "candidate.json", state)
    aggregate = _refresh_current(root)
    return {
        "ok": True,
        "schema_version": MATERIALIZATION_RECEIPT_SCHEMA,
        "owner": family.owner,
        "delivery_state": delivery_state,
        "release_digest": family.release_digest,
        "corpus_digest": family.corpus_digest,
        "distribution_digest": family.distribution_digest,
        "selection": state["selection"],
        "cache": state["cache"],
        "projection_impact": projection_impact,
        "receipt": str(receipt_path),
        "promoted": complete,
        "aggregate_state": aggregate["state"],
    }


def load_trusted_composition(
    composition_root: str | Path,
    trust_gate_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(composition_root).expanduser().resolve()
    payload = _read_json(root / "os-kag-composition.json", "OS KAG composition")
    if payload.get("schema_version") != COMPOSITION_SCHEMA:
        raise DistributionError("digest_mismatch", "composition schema mismatch")
    identity = _mapping(payload.get("composition_identity"), "composition identity")
    if (
        identity.get("artifact_class") != COMPOSITION_ARTIFACT_CLASS
        or identity.get("abi_epoch") != COMPOSITION_SCHEMA
    ):
        raise DistributionError("access_denied", "composition ABI mismatch")
    content_digest = _digest(
        identity.get("content_digest"), "composition content digest"
    )
    if content_digest != _composition_digest(payload):
        raise DistributionError("digest_mismatch", "composition digest mismatch")
    owners = _sequence(payload.get("owners"), "composition owners")
    names = [str(item.get("owner") or "") for item in owners]
    federation = _mapping(payload.get("federation"), "composition federation")
    if (
        len(owners) != OS_OWNER_COUNT
        or len(set(names)) != OS_OWNER_COUNT
        or federation.get("owner_count") != OS_OWNER_COUNT
    ):
        raise DistributionError(
            "rebuild_required", "composition does not contain 24 unique owners"
        )
    membership = _sha256_uri(_canonical_bytes(sorted(names)))
    if federation.get("membership_digest") != membership:
        raise DistributionError("digest_mismatch", "membership digest mismatch")
    for item in owners:
        _safe_owner(item.get("owner"))
        if _COMMIT_RE.fullmatch(str(item.get("source_ref") or "")) is None:
            raise DistributionError(
                "access_denied", "composition owner source ref is not exact"
            )
        for field in ("corpus_digest", "release_digest", "distribution_digest"):
            _digest(item.get(field), f"composition owner {field}")
        if item.get("verification_state") != "verified":
            raise DistributionError(
                "access_denied", "composition includes an unverified owner"
            )
    aggregate = _mapping(payload.get("aggregate"), "composition aggregate")
    if int(aggregate.get("git_hot_bytes") or OS_GIT_HOT_TARGET_BYTES + 1) > (
        OS_GIT_HOT_TARGET_BYTES
    ):
        raise DistributionError(
            "access_denied", "composition exceeds the Git-hot target"
        )
    signature = _mapping(payload.get("signature"), "composition signature")
    if (
        signature.get("verification_state") != "verified"
        or signature.get("subject_digest") != content_digest
    ):
        raise DistributionError(
            "access_denied", "composition signature is not verified"
        )
    gate = _read_json(
        Path(trust_gate_path).expanduser().resolve(), "abyss-machine trust gate"
    )
    trust = _slim_trust(
        gate,
        artifact_class=COMPOSITION_ARTIFACT_CLASS,
        content_digest=content_digest,
        source_repo="aoa-kag",
    )
    _require_subject_store_root(root, trust)
    return payload, trust


def activate_composition(
    composition: Mapping[str, Any],
    trust: Mapping[str, Any],
    runtime_root: str | Path,
) -> dict[str, Any]:
    root = Path(runtime_root).expanduser().resolve()
    owners = _sequence(composition.get("owners"), "composition owners")
    missing: list[str] = []
    mismatched: list[str] = []
    for entry in owners:
        owner = _safe_owner(entry.get("owner"))
        state = _read_optional(_owner_root(root, owner) / "current.json")
        if not state or state.get("delivery_state") != "complete":
            missing.append(owner)
            continue
        expected = {
            "source_ref": entry.get("source_ref"),
            "release_digest": entry.get("release_digest"),
            "corpus_digest": entry.get("corpus_digest"),
            "distribution_digest": entry.get("distribution_digest"),
        }
        if any(state.get(field) != value for field, value in expected.items()):
            mismatched.append(owner)
            continue
        if not _state_objects_present(root, state):
            mismatched.append(owner)
    if missing or mismatched:
        raise DistributionError(
            "rebuild_required",
            "composition cannot activate; "
            f"missing={','.join(missing[:8]) or '-'} "
            f"mismatched={','.join(mismatched[:8]) or '-'}",
        )
    identity = _mapping(
        composition.get("composition_identity"), "composition identity"
    )
    state = {
        "schema_version": COMPOSITION_STATE_SCHEMA,
        "activated_at": _now(),
        "composition_identity": dict(identity),
        "owner_count": len(owners),
        "owners": [
            {
                "owner": item.get("owner"),
                "source_ref": item.get("source_ref"),
                "release_digest": item.get("release_digest"),
                "corpus_digest": item.get("corpus_digest"),
                "distribution_digest": item.get("distribution_digest"),
            }
            for item in owners
        ],
        "aggregate": composition.get("aggregate"),
        "unresolved_references": composition.get("unresolved_references"),
        "trust": dict(trust),
        "canonical_truth": False,
    }
    composition_root = root / "distribution" / "composition"
    previous = _read_optional(composition_root / "current.json")
    if previous and previous.get("composition_identity") != state["composition_identity"]:
        write_json_atomic(composition_root / "last-good.json", previous)
    write_json_atomic(composition_root / "current.json", state)
    aggregate = _refresh_current(root)
    return {
        "ok": True,
        "schema_version": COMPOSITION_STATE_SCHEMA,
        "composition_identity": state["composition_identity"],
        "owner_count": len(owners),
        "aggregate_state": aggregate["state"],
    }


def rollback_owner(runtime_root: str | Path, owner: str) -> dict[str, Any]:
    root = Path(runtime_root).expanduser().resolve()
    owner_root = _owner_root(root, owner)
    current = _read_optional(owner_root / "current.json")
    last_good = _read_optional(owner_root / "last-good.json")
    if not last_good:
        raise DistributionError("rebuild_required", "owner has no last-good state")
    if (
        last_good.get("schema_version") != OWNER_STATE_SCHEMA
        or last_good.get("delivery_state") != "complete"
        or not _state_objects_present(root, last_good)
    ):
        raise DistributionError(
            "digest_mismatch", "owner last-good state is incomplete or corrupted"
        )
    rolled_back = {
        **last_good,
        "materialized_at": _now(),
        "rollback": {
            "from_release_digest": current.get("release_digest"),
            "to_release_digest": last_good.get("release_digest"),
        },
        "projection_impact": {
            "class": "owner_only",
            "affected_owners": [owner],
            "cross_owner_relations": "bounded_recompute_required",
        },
    }
    write_json_atomic(owner_root / "current.json", rolled_back)
    if current:
        write_json_atomic(owner_root / "last-good.json", current)
    receipt = {
        "schema_version": ROLLBACK_RECEIPT_SCHEMA,
        "owner": owner,
        "completed_at": _now(),
        "from_release_digest": current.get("release_digest"),
        "to_release_digest": rolled_back.get("release_digest"),
        "projection_impact": rolled_back["projection_impact"],
    }
    receipt_path = owner_root / "receipts" / (
        "rollback-" + receipt["completed_at"].replace(":", "-") + ".json"
    )
    write_json_atomic(receipt_path, receipt)
    aggregate = _refresh_current(root)
    return {
        "ok": True,
        **receipt,
        "receipt": str(receipt_path),
        "aggregate_state": aggregate["state"],
    }


def distribution_status(runtime_root: str | Path) -> dict[str, Any]:
    root = Path(runtime_root).expanduser().resolve()
    current = _read_optional(root / "distribution" / "current.json")
    return current or {
        "schema_version": CURRENT_STATE_SCHEMA,
        "state": "rebuild_available",
        "owners": [],
        "candidates": [],
        "summary": {
            "active_owner_count": 0,
            "candidate_owner_count": 0,
            "composition_active": False,
        },
        "degradation": [],
    }
