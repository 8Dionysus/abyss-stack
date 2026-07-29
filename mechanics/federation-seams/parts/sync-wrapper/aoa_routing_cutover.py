#!/usr/bin/env python3
"""Fail-closed intake for the receipt-bound canonical SDK routing producer.

This is deliberately separate from the non-canonical canary adapter.  It can
materialize SDK routing bytes as the live runtime mirror only when the exact
public-release trust verdict, subject store, owner-switch receipt, rollback
root, and operator change record agree.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa_routing_canary import (
    ABI_EPOCH,
    ARTIFACT_CLASS,
    DEFAULT_ROUTING_CONFIG,
    EXPECTED_CONTROLS,
    G5_AUTHORITY_FLAGS,
    CanaryError,
    absolute_existing_directory,
    absolute_existing_file,
    absolute_runtime_path,
    ensure_live_target_shape,
    file_digest_hex,
    is_live_target_shape,
    read_json,
    require_git_object_id,
    require_operator_change_ref,
    require_sha256_digest,
    resolved_subject_file,
    routing_required_files,
    safe_relative_path,
    stable_digest,
    validate_subject_store,
    write_json,
)


CANONICAL_POSTURE = "sdk_canonical"
OWNER_SWITCH_RECEIPT_SCHEMA = "aoa_sdk_routing_g5_owner_switch_receipt_v1"
OWNER_SWITCH_RECEIPT_REL = "succession/routing-g5-owner-switch.json"
CANONICAL_PROFILE_ID = "aoa-sdk-g5-canonical"
COMPATIBILITY_ROLLBACK_SCHEMA = (
    "abyss_stack_routing_g5_compatibility_rollback_v1"
)
COMPATIBILITY_ROLLBACK_REL = (
    "manifest/routing_g5_compatibility_rollback.json"
)
SDK_RUNTIME_ROLLBACK_BINDING_SCHEMA = (
    "abyss_stack_routing_sdk_runtime_rollback_binding_v1"
)
SDK_RUNTIME_ROLLBACK_RECEIPT_SCHEMA = (
    "abyss_stack_routing_sdk_runtime_rollback_receipt_v1"
)
SDK_RUNTIME_ROLLBACK_REL = (
    "manifest/routing_sdk_runtime_rollback.json"
)
CANONICAL_PREPARED_SUFFIX = ".sdk-canonical-prepared"
SDK_ROLLBACK_PREPARED_SUFFIX = ".sdk-rollback-prepared"
CANONICAL_AUTHORITY = {
    "archive_authorized": False,
    "canonical_producer_switch_authorized": True,
    "compatibility_window_started": True,
    "live_runtime_mutation_authorized": True,
    "predecessor_maintenance_only": True,
    "sdk_canonical": True,
}


class CutoverError(CanaryError):
    """A canonical cutover input or runtime state failed closed."""


def require_canonical_authority(value: Any, label: str) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise CutoverError(f"{label} must be an object")
    if set(value) != G5_AUTHORITY_FLAGS:
        missing = sorted(G5_AUTHORITY_FLAGS - set(value))
        extra = sorted(set(value) - G5_AUTHORITY_FLAGS)
        raise CutoverError(
            f"{label} authority fields drifted; missing={missing}, extra={extra}"
        )
    if value != CANONICAL_AUTHORITY:
        drift = sorted(
            key
            for key, expected in CANONICAL_AUTHORITY.items()
            if value.get(key) is not expected
        )
        raise CutoverError(
            f"{label} canonical authority values drifted: {', '.join(drift)}"
        )
    return dict(CANONICAL_AUTHORITY)


def owner_switch_receipt_digest(receipt: dict[str, Any]) -> str:
    return stable_digest(receipt)


def require_exact_controls(value: Any, label: str) -> None:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) for item in value)
        or len(value) != len(EXPECTED_CONTROLS)
        or set(value) != EXPECTED_CONTROLS
    ):
        raise CutoverError(f"{label} drifted")


def require_string_list_contains(
    value: Any,
    expected: str,
    label: str,
) -> None:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) for item in value)
        or expected not in value
    ):
        raise CutoverError(f"{label} lacks {expected}")


def exact_subject_ledger(
    entries: dict[str, dict[str, Any]],
    *,
    subject_digest: str,
) -> list[dict[str, Any]]:
    ledger = sorted(
        (dict(entry) for entry in entries.values()),
        key=lambda entry: str(entry.get("path") or ""),
    )
    if stable_digest(ledger) != subject_digest:
        raise CutoverError(
            "canonical routing subject ledger does not match its admitted digest"
        )
    return ledger


def validate_embedded_subject_ledger(
    value: Any,
    *,
    subject_digest: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise CutoverError(
            "canonical routing embedded subject ledger is missing"
        )
    if stable_digest(value) != subject_digest:
        raise CutoverError(
            "canonical routing embedded subject ledger aggregate drifted"
        )
    entries: dict[str, dict[str, Any]] = {}
    for index, raw_entry in enumerate(value):
        if not isinstance(raw_entry, dict):
            raise CutoverError(
                "canonical routing embedded subject ledger entry must be an "
                f"object: {index}"
            )
        relative = safe_relative_path(
            raw_entry.get("path"),
            f"canonical routing embedded subject ledger[{index}].path",
        )
        if relative in entries:
            raise CutoverError(
                "canonical routing embedded subject ledger has a duplicate "
                f"entry: {relative}"
            )
        sha256_hex = str(raw_entry.get("sha256_hex") or "")
        sha256 = require_sha256_digest(
            str(raw_entry.get("sha256") or ""),
            f"canonical routing embedded subject ledger digest for {relative}",
        )
        if sha256 != f"sha256:{sha256_hex}":
            raise CutoverError(
                "canonical routing embedded subject ledger digest forms "
                f"disagree: {relative}"
            )
        if (
            len(sha256_hex) != 64
            or any(ch not in "0123456789abcdef" for ch in sha256_hex)
            or not isinstance(raw_entry.get("bytes"), int)
            or raw_entry["bytes"] < 0
            or not isinstance(raw_entry.get("role"), str)
            or not raw_entry["role"]
        ):
            raise CutoverError(
                "canonical routing embedded subject ledger entry is invalid: "
                f"{relative}"
            )
        entries[relative] = raw_entry
    return entries


def sdk_runtime_rollback_binding(
    *,
    rollback_root: Path,
    sdk_source_ref: str,
    subject_digest: str,
) -> dict[str, Any]:
    return {
        "schema": SDK_RUNTIME_ROLLBACK_BINDING_SCHEMA,
        "owner_repo": "aoa-sdk",
        "source_ref": sdk_source_ref,
        "artifact_subject_digest": subject_digest,
        "root_name": rollback_root.name,
        "posture": "primary_operational_rollback",
        "predecessor_implementation_required": False,
        "archive_authorized": False,
    }


def validate_sdk_runtime_rollback_binding(
    value: Any,
    *,
    sdk_source_ref: str,
    subject_digest: str,
    rollback_root_name: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CutoverError("SDK runtime rollback binding is missing")
    expected = {
        "schema": SDK_RUNTIME_ROLLBACK_BINDING_SCHEMA,
        "owner_repo": "aoa-sdk",
        "source_ref": sdk_source_ref,
        "artifact_subject_digest": subject_digest,
        "posture": "primary_operational_rollback",
        "predecessor_implementation_required": False,
        "archive_authorized": False,
    }
    if rollback_root_name is not None:
        expected["root_name"] = rollback_root_name
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise CutoverError(
                f"SDK runtime rollback binding drifted: {key}"
            )
    root_name = value.get("root_name")
    if (
        not isinstance(root_name, str)
        or not root_name
        or Path(root_name).name != root_name
        or root_name in {".", ".."}
    ):
        raise CutoverError("SDK runtime rollback root name is invalid")
    return dict(value)


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        raise CutoverError(
            "routing cutover requires directory fsync support"
        )
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_tree(root: Path) -> None:
    files: list[Path] = []
    directories: list[Path] = [root]
    for path in root.rglob("*"):
        if path.is_symlink():
            raise CutoverError(
                f"routing transaction tree must not contain symlinks: {path}"
            )
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            directories.append(path)
    for path in sorted(files):
        fsync_file(path)
    for path in sorted(
        directories,
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        fsync_directory(path)


def resolved_tree_file(root: Path, relative: str, label: str) -> Path:
    normalized = safe_relative_path(relative, label)
    resolved_root = root.resolve(strict=True)
    candidate = root / normalized
    if candidate.is_symlink():
        raise CutoverError(f"{label} must not be a symlink: {normalized}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (FileNotFoundError, ValueError) as exc:
        raise CutoverError(
            f"{label} is missing or escapes its root: {normalized}"
        ) from exc
    if not resolved.is_file():
        raise CutoverError(f"{label} is not a file: {normalized}")
    return resolved


def validate_predecessor_root(
    root: Path,
    *,
    required_files: list[str],
    predecessor_source_ref: str,
    allow_compatibility_marker: bool = False,
) -> dict[str, Any]:
    if (
        (root / COMPATIBILITY_ROLLBACK_REL).exists()
        and not allow_compatibility_marker
    ):
        raise CutoverError(
            "predecessor rollback tree already carries a compatibility "
            "rollback marker"
        )
    manifest_path = resolved_tree_file(
        root,
        "manifest/federation_mirror_manifest.json",
        "predecessor rollback manifest",
    )
    manifest = read_json(
        manifest_path,
        "predecessor rollback manifest",
    )
    expected = {
        "schema": "abyss_stack_federation_mirror_manifest_v1",
        "layer": "aoa-routing",
        "source_git_commit": predecessor_source_ref,
        "required_file_count": len(required_files),
        "required_files": required_files,
        "mirror_is_authority": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise CutoverError(f"predecessor rollback manifest drifted: {key}")
    if manifest.get("routing_producer_posture") not in {
        None,
        "predecessor_canonical",
    }:
        raise CutoverError(
            "predecessor rollback tree claims an incompatible producer posture"
        )
    hashes = manifest.get("file_sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(required_files):
        raise CutoverError("predecessor rollback manifest hash set drifted")
    for relative in required_files:
        source = resolved_tree_file(
            root,
            relative,
            "predecessor rollback file",
        )
        if hashes.get(relative) != file_digest_hex(source):
            raise CutoverError(
                f"predecessor rollback file digest drifted: {relative}"
            )
    router_path = resolved_tree_file(
        root,
        "generated/aoa_router.min.json",
        "predecessor rollback router",
    )
    router = read_json(
        router_path,
        "predecessor rollback router",
    )
    identity = router.get("artifact_identity")
    if (
        not isinstance(identity, dict)
        or identity.get("owner_repo") != "aoa-routing"
        or identity.get("artifact_class") != ARTIFACT_CLASS
        or identity.get("abi_epoch") != ABI_EPOCH
    ):
        raise CutoverError(
            "predecessor rollback identity is not the exact stable routing ABI"
        )
    compact_identity = {
        "owner_repo": identity["owner_repo"],
        "artifact_class": identity["artifact_class"],
        "abi_epoch": identity["abi_epoch"],
    }
    return {
        "verified": True,
        "source_ref": predecessor_source_ref,
        "required_file_count": len(required_files),
        "manifest_digest": stable_digest(manifest),
        "file_hashes_digest": stable_digest(hashes),
        "artifact_identity": compact_identity,
    }


def compatibility_rollback_marker(
    *,
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    operator_change_ref: str,
    predecessor_inspection: dict[str, Any],
    rolled_back_at: str,
) -> dict[str, Any]:
    return {
        "schema": COMPATIBILITY_ROLLBACK_SCHEMA,
        "state": "compatibility_rollback_active",
        "source_owner_state": "sdk_canonical_unchanged",
        "sdk_source_ref": sdk_source_ref,
        "predecessor_source_ref": predecessor_source_ref,
        "artifact_subject_digest": subject_digest,
        "operator_change_ref": operator_change_ref,
        "rolled_back_at_utc": rolled_back_at,
        "predecessor_manifest_digest": predecessor_inspection[
            "manifest_digest"
        ],
        "predecessor_file_hashes_digest": predecessor_inspection[
            "file_hashes_digest"
        ],
        "predecessor_artifact_identity": predecessor_inspection[
            "artifact_identity"
        ],
        "archive_authorized": False,
    }


def validate_compatibility_rollback_marker(
    marker: dict[str, Any],
    *,
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    operator_change_ref: str,
    predecessor_inspection: dict[str, Any],
) -> None:
    expected = {
        "schema": COMPATIBILITY_ROLLBACK_SCHEMA,
        "state": "compatibility_rollback_active",
        "source_owner_state": "sdk_canonical_unchanged",
        "sdk_source_ref": sdk_source_ref,
        "predecessor_source_ref": predecessor_source_ref,
        "artifact_subject_digest": subject_digest,
        "operator_change_ref": operator_change_ref,
        "predecessor_manifest_digest": predecessor_inspection[
            "manifest_digest"
        ],
        "predecessor_file_hashes_digest": predecessor_inspection[
            "file_hashes_digest"
        ],
        "predecessor_artifact_identity": predecessor_inspection[
            "artifact_identity"
        ],
        "archive_authorized": False,
    }
    for key, value in expected.items():
        if marker.get(key) != value:
            raise CutoverError(
                f"compatibility rollback marker drifted: {key}"
            )
    if not isinstance(marker.get("rolled_back_at_utc"), str) or not marker.get(
        "rolled_back_at_utc"
    ):
        raise CutoverError(
            "compatibility rollback marker timestamp is missing"
        )


def validate_owner_switch_receipt(
    receipt: dict[str, Any],
    *,
    sdk_source_ref: str,
    predecessor_source_ref: str,
) -> dict[str, Any]:
    if receipt.get("schema") != OWNER_SWITCH_RECEIPT_SCHEMA:
        raise CutoverError("owner-switch receipt schema is invalid")
    if receipt.get("status") not in {
        "g5_switch_authorized",
        "g5_switch_executed",
    }:
        raise CutoverError("owner-switch receipt status is not cutover-capable")
    transition = receipt.get("transition")
    if not isinstance(transition, dict):
        raise CutoverError("owner-switch receipt transition is missing")
    expected_transition = {
        "from_state": "predecessor_canonical",
        "to_state": "sdk_canonical",
        "canonical_owner_before": "aoa-routing",
        "canonical_owner_after": "aoa-sdk",
    }
    for key, expected in expected_transition.items():
        if transition.get(key) != expected:
            raise CutoverError(f"owner-switch receipt transition drifted: {key}")
    sdk = receipt.get("sdk")
    sdk_version = sdk.get("version") if isinstance(sdk, dict) else None
    if (
        not isinstance(sdk, dict)
        or sdk.get("owner_repo") != "aoa-sdk"
        or sdk.get("source_ref") != sdk_source_ref
        or sdk.get("abi_epoch") != ABI_EPOCH
        or not isinstance(sdk_version, str)
        or not sdk_version
    ):
        raise CutoverError("owner-switch receipt SDK binding drifted")
    predecessor = receipt.get("predecessor")
    if (
        not isinstance(predecessor, dict)
        or predecessor.get("owner_repo") != "aoa-routing"
        or predecessor.get("source_ref") != predecessor_source_ref
        or predecessor.get("rollback_posture") != "retained"
    ):
        raise CutoverError("owner-switch receipt predecessor binding drifted")
    compatibility = receipt.get("compatibility_window")
    started_on = (
        compatibility.get("started_on")
        if isinstance(compatibility, dict)
        else None
    )
    if not isinstance(started_on, str):
        raise CutoverError("owner-switch receipt compatibility window is invalid")
    try:
        parsed_started_on = datetime.strptime(started_on, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CutoverError(
            "owner-switch receipt compatibility start date is invalid"
        ) from exc
    if (
        compatibility.get("state") != "started"
        or parsed_started_on.isoformat() != started_on
        or compatibility.get("started_by_sdk_version") != sdk_version
    ):
        raise CutoverError("owner-switch receipt compatibility window is invalid")
    release = receipt.get("public_release")
    if not isinstance(release, dict):
        raise CutoverError("owner-switch receipt public release binding is missing")
    require_sha256_digest(
        str(release.get("asset_digest") or ""),
        "owner-switch receipt release asset digest",
    )
    if not isinstance(release.get("release_ref"), str) or not release.get(
        "release_ref"
    ):
        raise CutoverError("owner-switch receipt release ref is missing")
    require_canonical_authority(
        receipt.get("g5_authority"),
        "owner-switch receipt g5_authority",
    )
    if receipt.get("archive_stop_line") != (
        "Repository archival remains forbidden without consumer-zero, "
        "compatibility exit, and separate exact operator approval."
    ):
        raise CutoverError("owner-switch receipt archive stop line drifted")
    return receipt


def validate_canonical_trust_verdict(
    verdict: dict[str, Any],
    *,
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    receipt: dict[str, Any],
) -> dict[str, bool]:
    expected = {
        "schema": "abyss_machine_artifact_trust_gate_v1",
        "ok": True,
        "artifact_class": ARTIFACT_CLASS,
        "consumer_intent": "runtime",
        "subject_digest": subject_digest,
        "require_latest": True,
    }
    for key, value in expected.items():
        if verdict.get(key) != value:
            raise CutoverError(f"canonical trust verdict field drifted: {key}")
    if verdict.get("verdict") not in {"allow", "warn"}:
        raise CutoverError("canonical trust verdict does not admit runtime")
    if verdict.get("reasons") or verdict.get("blockers"):
        raise CutoverError("canonical trust verdict contains blockers")
    record_id = verdict.get("record_id")
    if (
        not isinstance(record_id, str)
        or not record_id
        or verdict.get("latest_record_id") != record_id
    ):
        raise CutoverError("canonical trust verdict latest-record binding drifted")
    decision = verdict.get("decision")
    if (
        not isinstance(decision, dict)
        or decision.get("model") != "fail_closed_consumer_admission"
        or decision.get("allow") is not True
        or decision.get("consumer_intent") != "runtime"
    ):
        raise CutoverError("canonical trust decision is invalid")

    record = verdict.get("record")
    if not isinstance(record, dict):
        raise CutoverError("canonical trust record is missing")
    expected_record = {
        "record_id": record_id,
        "artifact_class": ARTIFACT_CLASS,
        "source_repo": "aoa-sdk",
        "source_ref": sdk_source_ref,
        "artifact_subjects_digest": subject_digest,
        "latest_eligible": True,
        "terminal_state": False,
        "verification_ok": True,
        "trust_root_mode": "public_release",
    }
    for key, value in expected_record.items():
        if record.get(key) != value:
            raise CutoverError(f"canonical trust record field drifted: {key}")
    if record.get("lifecycle_state") not in {"release-ready", "published"}:
        raise CutoverError("canonical trust record lifecycle is not release-ready")
    require_string_list_contains(
        record.get("consumer_refs"),
        "abyss-stack:routing-canonical",
        "canonical trust record consumer admission",
    )
    require_exact_controls(
        record.get("required_controls"),
        "canonical trust record required controls",
    )
    require_exact_controls(
        record.get("verified_controls"),
        "canonical trust record verified controls",
    )
    store = record.get("artifact_subject_store")
    if (
        not isinstance(store, dict)
        or store.get("required") is not True
        or store.get("ok") is not True
        or store.get("aggregate_digest") != subject_digest
    ):
        raise CutoverError("canonical trust record exact subject store is invalid")

    admission = record.get("producer_admission")
    if not isinstance(admission, dict):
        raise CutoverError("canonical producer admission is missing")
    expected_admission = {
        "schema": "abyss_machine_artifact_producer_admission_v1",
        "status": "canonical_producer",
        "profile_id": CANONICAL_PROFILE_ID,
        "owner_repo": "aoa-sdk",
        "source_ref": sdk_source_ref,
        "canonical_owner_repo": "aoa-sdk",
        "canonical_predecessor_source_ref": predecessor_source_ref,
        "runtime_consumer": "abyss-stack",
        "stronger_owner": "abyss-machine",
        "provenance_state": "sdk_canonical",
        "publication_posture": "public_release_canonical",
        "single_canonical_owner": True,
        "canonical_switch_authorized": True,
    }
    for key, value in expected_admission.items():
        if admission.get(key) != value:
            raise CutoverError(f"canonical producer admission field drifted: {key}")
    require_string_list_contains(
        admission.get("allowed_consumer_intents"),
        "runtime",
        "canonical producer admission consumer intent",
    )
    require_exact_controls(
        admission.get("required_controls"),
        "canonical producer admission controls",
    )
    authority = require_canonical_authority(
        admission.get("g5_authority"),
        "canonical producer admission g5_authority",
    )
    receipt_summary = admission.get("owner_switch_receipt")
    if (
        not isinstance(receipt_summary, dict)
        or receipt_summary.get("schema") != OWNER_SWITCH_RECEIPT_SCHEMA
        or receipt_summary.get("digest") != owner_switch_receipt_digest(receipt)
        or receipt_summary.get("status") != receipt.get("status")
    ):
        raise CutoverError("canonical producer admission receipt binding drifted")

    inspected = verdict.get("inspected_claims")
    if not isinstance(inspected, dict):
        raise CutoverError("canonical trust inspected claims are missing")
    subject_identity = inspected.get("subject_identity")
    registry_latest = inspected.get("registry_latest")
    source = inspected.get("source")
    trust_root = inspected.get("trust_root")
    inspected_store = inspected.get("artifact_subject_store")
    inspected_admission = inspected.get("producer_admission")
    if (
        not isinstance(subject_identity, dict)
        or subject_identity.get("subject_digest_expected") != subject_digest
        or subject_identity.get("subject_digest_matched") is not True
    ):
        raise CutoverError("canonical inspected subject identity is invalid")
    if (
        not isinstance(registry_latest, dict)
        or registry_latest.get("required") is not True
        or registry_latest.get("selected_record_is_latest") is not True
    ):
        raise CutoverError("canonical inspected latest-record claim is invalid")
    if (
        not isinstance(source, dict)
        or source.get("source_repo_matched") is not True
        or source.get("source_ref_matched") is not True
        or source.get("source_ref_actual") != sdk_source_ref
    ):
        raise CutoverError("canonical inspected source claim is invalid")
    if (
        not isinstance(trust_root, dict)
        or trust_root.get("trust_root_mode_actual") != "public_release"
        or trust_root.get("trust_root_mode_matched") is not True
    ):
        raise CutoverError("canonical inspected public-release root is invalid")
    if (
        not isinstance(inspected_store, dict)
        or inspected_store.get("ok") is not True
        or inspected_store.get("aggregate_digest") != subject_digest
    ):
        raise CutoverError("canonical inspected subject store is invalid")
    if inspected_admission != admission:
        raise CutoverError("canonical inspected producer admission drifted")
    return authority


def validate_inputs(
    args: argparse.Namespace,
) -> tuple[
    list[str],
    dict[str, bool],
    dict[str, dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    sdk_ref = require_git_object_id(args.sdk_source_ref, "SDK source ref")
    predecessor_ref = require_git_object_id(
        args.predecessor_source_ref,
        "predecessor source ref",
    )
    digest = require_sha256_digest(args.subject_digest, "subject digest")
    config = absolute_existing_file(args.routing_config, "routing config")
    store = absolute_existing_directory(args.subject_store, "subject store")
    verdict_path = absolute_existing_file(args.trust_verdict, "trust verdict")
    receipt_path = absolute_existing_file(
        args.owner_switch_receipt,
        "owner-switch receipt",
    )
    try:
        receipt_relative = receipt_path.relative_to(store)
    except ValueError as exc:
        raise CutoverError(
            "owner-switch receipt must be a file in the exact subject store"
        ) from exc
    if receipt_relative.as_posix() != OWNER_SWITCH_RECEIPT_REL:
        raise CutoverError(
            "owner-switch receipt must use the canonical subject path "
            f"{OWNER_SWITCH_RECEIPT_REL}"
        )
    required = routing_required_files(config)
    entries = validate_subject_store(
        store,
        required_files=[*required, OWNER_SWITCH_RECEIPT_REL],
        subject_digest=digest,
        consumer_intent="runtime",
    )
    receipt = validate_owner_switch_receipt(
        read_json(receipt_path, "owner-switch receipt"),
        sdk_source_ref=sdk_ref,
        predecessor_source_ref=predecessor_ref,
    )
    verdict = read_json(verdict_path, "trust verdict")
    authority = validate_canonical_trust_verdict(
        verdict,
        sdk_source_ref=sdk_ref,
        predecessor_source_ref=predecessor_ref,
        subject_digest=digest,
        receipt=receipt,
    )
    return required, authority, entries, receipt, verdict


def canonical_manifest(
    *,
    target_root: Path,
    required_files: list[str],
    subject_entries: dict[str, dict[str, Any]],
    trust_verdict: dict[str, Any],
    receipt: dict[str, Any],
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    authority: dict[str, bool],
    observed_at: str,
    activation_mode: str,
    operator_change_ref: str | None,
) -> dict[str, Any]:
    return {
        "schema": "abyss_stack_federation_mirror_manifest_v1",
        "layer": "aoa-routing",
        "routing_producer_posture": CANONICAL_POSTURE,
        "cutover_activation_mode": activation_mode,
        "operator_change_ref": operator_change_ref,
        "source_git_commit": sdk_source_ref,
        "generated_at_utc": observed_at,
        "refresh_command": (
            "scripts/aoa-routing-cutover materialize --explicit-exact-inputs"
        ),
        "required_file_count": len(required_files),
        "required_files": required_files,
        "file_sha256": {
            relative: file_digest_hex(target_root / relative)
            for relative in required_files
        },
        "artifact_subject_digest": subject_digest,
        "artifact_subject_ledger": exact_subject_ledger(
            subject_entries,
            subject_digest=subject_digest,
        ),
        "mirror_is_authority": False,
        "canonical_producer": {
            "owner_repo": "aoa-sdk",
            "source_ref": sdk_source_ref,
        },
        "predecessor_rollback": {
            "owner_repo": "aoa-routing",
            "source_ref": predecessor_source_ref,
            "posture": "compatibility_security_rollback_deprecation_only",
        },
        "g5_authority": authority,
        "owner_switch_receipt": receipt,
        "owner_switch_receipt_digest": owner_switch_receipt_digest(receipt),
        "trust_verdict": trust_verdict,
    }


def validate_canonical_root(
    target_root: Path,
    *,
    required_files: list[str],
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    subject_entries: dict[str, dict[str, Any]],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    manifest = read_json(
        target_root / "manifest" / "federation_mirror_manifest.json",
        "canonical routing mirror manifest",
    )
    expected = {
        "schema": "abyss_stack_federation_mirror_manifest_v1",
        "layer": "aoa-routing",
        "routing_producer_posture": CANONICAL_POSTURE,
        "source_git_commit": sdk_source_ref,
        "artifact_subject_digest": subject_digest,
        "mirror_is_authority": False,
        "required_file_count": len(required_files),
        "required_files": required_files,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise CutoverError(f"canonical routing manifest field drifted: {key}")
    activation = manifest.get("cutover_activation_mode")
    operator_change = manifest.get("operator_change_ref")
    if activation not in {"isolated", "authorized_live_cutover"}:
        raise CutoverError("canonical routing activation mode is invalid")
    if activation == "authorized_live_cutover":
        require_operator_change_ref(operator_change)
    elif operator_change is not None:
        raise CutoverError("isolated canonical check claims an operator change")
    if manifest.get("canonical_producer") != {
        "owner_repo": "aoa-sdk",
        "source_ref": sdk_source_ref,
    }:
        raise CutoverError("canonical routing producer binding drifted")
    rollback = manifest.get("predecessor_rollback")
    if (
        not isinstance(rollback, dict)
        or rollback.get("owner_repo") != "aoa-routing"
        or rollback.get("source_ref") != predecessor_source_ref
        or rollback.get("posture")
        != "compatibility_security_rollback_deprecation_only"
    ):
        raise CutoverError("canonical routing predecessor rollback binding drifted")
    sdk_rollback = manifest.get("sdk_runtime_rollback")
    if sdk_rollback is not None:
        validate_sdk_runtime_rollback_binding(
            sdk_rollback,
            sdk_source_ref=sdk_source_ref,
            subject_digest=subject_digest,
        )
    authority = require_canonical_authority(
        manifest.get("g5_authority"),
        "canonical routing manifest g5_authority",
    )
    if manifest.get("owner_switch_receipt") != receipt:
        raise CutoverError("canonical routing owner-switch receipt drifted")
    if manifest.get("owner_switch_receipt_digest") != owner_switch_receipt_digest(
        receipt
    ):
        raise CutoverError("canonical routing owner-switch receipt digest drifted")
    embedded_entries = validate_embedded_subject_ledger(
        manifest.get("artifact_subject_ledger"),
        subject_digest=subject_digest,
    )
    if embedded_entries != subject_entries:
        raise CutoverError(
            "canonical routing embedded subject ledger differs from the "
            "admitted subject-store ledger"
        )
    validate_canonical_trust_verdict(
        manifest.get("trust_verdict")
        if isinstance(manifest.get("trust_verdict"), dict)
        else {},
        sdk_source_ref=sdk_source_ref,
        predecessor_source_ref=predecessor_source_ref,
        subject_digest=subject_digest,
        receipt=receipt,
    )
    hashes = manifest.get("file_sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(required_files):
        raise CutoverError("canonical routing manifest hash set drifted")
    for relative in required_files:
        materialized = resolved_subject_file(target_root, relative)
        actual = file_digest_hex(materialized)
        if hashes.get(relative) != actual:
            raise CutoverError(
                f"canonical routing materialized file digest drifted: {relative}"
            )
        if actual != subject_entries[relative].get("sha256_hex"):
            raise CutoverError(
                "canonical routing file no longer matches the subject-store "
                f"ledger: {relative}"
            )
    router = read_json(
        target_root / "generated" / "aoa_router.min.json",
        "routing router",
    )
    identity = router.get("artifact_identity")
    if (
        not isinstance(identity, dict)
        or identity.get("owner_repo") != "aoa-sdk"
        or identity.get("artifact_class") != ARTIFACT_CLASS
        or identity.get("abi_epoch") != ABI_EPOCH
    ):
        raise CutoverError("canonical routing identity is not the SDK stable ABI")
    return {
        "ok": True,
        "schema": "abyss_stack_routing_g5_cutover_check_v1",
        "posture": CANONICAL_POSTURE,
        "target_root": str(target_root),
        "sdk_source_ref": sdk_source_ref,
        "canonical_predecessor_source_ref": predecessor_source_ref,
        "artifact_subject_digest": subject_digest,
        "required_file_count": len(required_files),
        "owner_switch_receipt_digest": owner_switch_receipt_digest(receipt),
        "g5_authority": authority,
        "canonical_switch_authorized": True,
        "closure_authorized": True,
        "activation_mode": activation,
        "operator_change_ref_present": isinstance(operator_change, str),
        "sdk_runtime_rollback_ready": sdk_rollback is not None,
        "predecessor_implementation_required": (
            False if sdk_rollback is not None else None
        ),
    }


def validate_live_canonical_root(
    target_root: Path,
    *,
    required_files: list[str],
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    subject_entries: dict[str, dict[str, Any]],
    receipt: dict[str, Any],
    operator_change_ref: str,
) -> dict[str, Any]:
    result = validate_canonical_root(
        target_root,
        required_files=required_files,
        sdk_source_ref=sdk_source_ref,
        predecessor_source_ref=predecessor_source_ref,
        subject_digest=subject_digest,
        subject_entries=subject_entries,
        receipt=receipt,
    )
    manifest = read_json(
        target_root / "manifest" / "federation_mirror_manifest.json",
        "live canonical routing mirror manifest",
    )
    if manifest.get("cutover_activation_mode") != "authorized_live_cutover":
        raise CutoverError(
            "live canonical routing activation mode drifted"
        )
    if manifest.get("operator_change_ref") != operator_change_ref:
        raise CutoverError(
            "live canonical routing operator change ref drifted"
        )
    return result


def prepare_canonical_stage(
    *,
    prepared: Path,
    target: Path,
    store: Path,
    required_files: list[str],
    entries: dict[str, dict[str, Any]],
    verdict: dict[str, Any],
    receipt: dict[str, Any],
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    authority: dict[str, bool],
    observed_at: str | None,
    live: bool,
    operator_change_ref: str | None,
) -> dict[str, Any]:
    if prepared.is_symlink():
        raise CutoverError("canonical prepared stage must not be a symlink")
    if prepared.exists():
        if not prepared.is_dir():
            raise CutoverError(
                "canonical prepared stage exists but is not a directory"
            )
        if live:
            assert operator_change_ref is not None
            return validate_live_canonical_root(
                prepared,
                required_files=required_files,
                sdk_source_ref=sdk_source_ref,
                predecessor_source_ref=predecessor_source_ref,
                subject_digest=subject_digest,
                subject_entries=entries,
                receipt=receipt,
                operator_change_ref=operator_change_ref,
            )
        return validate_canonical_root(
            prepared,
            required_files=required_files,
            sdk_source_ref=sdk_source_ref,
            predecessor_source_ref=predecessor_source_ref,
            subject_digest=subject_digest,
            subject_entries=entries,
            receipt=receipt,
        )

    build = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.sdk-canonical-build-",
            dir=target.parent,
        )
    )
    try:
        for relative in required_files:
            source = resolved_subject_file(store, relative)
            destination = build / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if file_digest_hex(destination) != entries[relative].get(
                "sha256_hex"
            ):
                raise CutoverError(
                    "copied canonical file does not match subject ledger: "
                    f"{relative}"
                )
        generated_at = observed_at or datetime.now(timezone.utc).isoformat()
        manifest = canonical_manifest(
            target_root=build,
            required_files=required_files,
            subject_entries=entries,
            trust_verdict=verdict,
            receipt=receipt,
            sdk_source_ref=sdk_source_ref,
            predecessor_source_ref=predecessor_source_ref,
            subject_digest=subject_digest,
            authority=authority,
            observed_at=generated_at,
            activation_mode=(
                "authorized_live_cutover" if live else "isolated"
            ),
            operator_change_ref=operator_change_ref if live else None,
        )
        write_json(
            build / "manifest" / "federation_mirror_manifest.json",
            manifest,
        )
        if live:
            assert operator_change_ref is not None
            result = validate_live_canonical_root(
                build,
                required_files=required_files,
                sdk_source_ref=sdk_source_ref,
                predecessor_source_ref=predecessor_source_ref,
                subject_digest=subject_digest,
                subject_entries=entries,
                receipt=receipt,
                operator_change_ref=operator_change_ref,
            )
        else:
            result = validate_canonical_root(
                build,
                required_files=required_files,
                sdk_source_ref=sdk_source_ref,
                predecessor_source_ref=predecessor_source_ref,
                subject_digest=subject_digest,
                subject_entries=entries,
                receipt=receipt,
            )
        fsync_tree(build)
        os.replace(build, prepared)
        fsync_directory(prepared.parent)
        return result
    finally:
        if build.exists():
            shutil.rmtree(build)


def validate_sdk_refresh_source_root(
    target_root: Path,
    *,
    required_files: list[str],
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    subject_entries: dict[str, dict[str, Any]],
    receipt: dict[str, Any],
    trust_verdict: dict[str, Any],
) -> dict[str, Any]:
    """Validate an older SDK-canonical mirror before metadata refresh.

    The first live SDK cutover predates the self-contained subject ledger.
    This validator permits that one missing field, but it still binds every
    runtime byte, owner receipt, authority flag, and durable trust record to
    the exact current inputs before the manifest can be replaced.
    """

    manifest = read_json(
        target_root / "manifest" / "federation_mirror_manifest.json",
        "SDK refresh source manifest",
    )
    expected = {
        "schema": "abyss_stack_federation_mirror_manifest_v1",
        "layer": "aoa-routing",
        "routing_producer_posture": CANONICAL_POSTURE,
        "cutover_activation_mode": "authorized_live_cutover",
        "source_git_commit": sdk_source_ref,
        "artifact_subject_digest": subject_digest,
        "mirror_is_authority": False,
        "required_file_count": len(required_files),
        "required_files": required_files,
        "canonical_producer": {
            "owner_repo": "aoa-sdk",
            "source_ref": sdk_source_ref,
        },
    }
    for key, expected_value in expected.items():
        if manifest.get(key) != expected_value:
            raise CutoverError(
                f"SDK refresh source manifest field drifted: {key}"
            )
    predecessor = manifest.get("predecessor_rollback")
    if (
        not isinstance(predecessor, dict)
        or predecessor.get("owner_repo") != "aoa-routing"
        or predecessor.get("source_ref") != predecessor_source_ref
        or predecessor.get("posture")
        != "compatibility_security_rollback_deprecation_only"
        or predecessor.get("operationally_required") not in {None, False}
    ):
        raise CutoverError(
            "SDK refresh source predecessor binding drifted"
        )
    require_operator_change_ref(manifest.get("operator_change_ref"))
    require_canonical_authority(
        manifest.get("g5_authority"),
        "SDK refresh source g5_authority",
    )
    if manifest.get("owner_switch_receipt") != receipt:
        raise CutoverError("SDK refresh source owner-switch receipt drifted")
    if manifest.get("owner_switch_receipt_digest") != owner_switch_receipt_digest(
        receipt
    ):
        raise CutoverError(
            "SDK refresh source owner-switch receipt digest drifted"
        )
    existing_verdict = manifest.get("trust_verdict")
    if not isinstance(existing_verdict, dict):
        raise CutoverError("SDK refresh source trust verdict is missing")
    validate_canonical_trust_verdict(
        existing_verdict,
        sdk_source_ref=sdk_source_ref,
        predecessor_source_ref=predecessor_source_ref,
        subject_digest=subject_digest,
        receipt=receipt,
    )
    if existing_verdict.get("record_id") != trust_verdict.get("record_id"):
        raise CutoverError(
            "SDK refresh source and supplied trust records disagree"
        )
    hashes = manifest.get("file_sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(required_files):
        raise CutoverError("SDK refresh source hash set drifted")
    for relative in required_files:
        materialized = resolved_subject_file(target_root, relative)
        actual = file_digest_hex(materialized)
        if hashes.get(relative) != actual:
            raise CutoverError(
                f"SDK refresh source file digest drifted: {relative}"
            )
        if actual != subject_entries[relative].get("sha256_hex"):
            raise CutoverError(
                "SDK refresh source no longer matches the admitted "
                f"subject ledger: {relative}"
            )
    embedded = manifest.get("artifact_subject_ledger")
    legacy_manifest = embedded is None
    if not legacy_manifest:
        embedded_entries = validate_embedded_subject_ledger(
            embedded,
            subject_digest=subject_digest,
        )
        if embedded_entries != subject_entries:
            raise CutoverError(
                "SDK refresh source embedded ledger differs from admission"
            )
    router = read_json(
        target_root / "generated" / "aoa_router.min.json",
        "SDK refresh source router",
    )
    identity = router.get("artifact_identity")
    if (
        not isinstance(identity, dict)
        or identity.get("owner_repo") != "aoa-sdk"
        or identity.get("artifact_class") != ARTIFACT_CLASS
        or identity.get("abi_epoch") != ABI_EPOCH
    ):
        raise CutoverError("SDK refresh source is not the SDK stable ABI")
    return {
        "verified": True,
        "legacy_manifest_without_subject_ledger": legacy_manifest,
        "previous_manifest_digest": stable_digest(manifest),
        "trust_record_id": existing_verdict.get("record_id"),
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.stage-",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        write_json(temporary_path, payload)
        fsync_file(temporary_path)
        os.replace(temporary_path, path)
        fsync_directory(path.parent)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def refresh_materialized(args: argparse.Namespace) -> dict[str, Any]:
    """Refresh a live SDK mirror and establish SDK-only rollback bytes."""

    required, authority, entries, receipt, verdict = validate_inputs(args)
    target = absolute_existing_directory(args.target_root, "target root")
    ensure_live_target_shape(target)
    if not args.authorized_live_cutover:
        raise CutoverError(
            "SDK materialized refresh requires --authorized-live-cutover"
        )
    operator_change = require_operator_change_ref(args.operator_change_ref)
    rollback_root = absolute_runtime_path(
        args.sdk_rollback_root,
        "SDK rollback root",
    )
    if (
        rollback_root == target
        or rollback_root in target.parents
        or target in rollback_root.parents
    ):
        raise CutoverError("target and SDK rollback roots must be disjoint")
    if rollback_root.parent != target.parent:
        raise CutoverError(
            "SDK rollback root must share the target parent"
        )
    source_inspection = validate_sdk_refresh_source_root(
        target,
        required_files=required,
        sdk_source_ref=args.sdk_source_ref,
        predecessor_source_ref=args.predecessor_source_ref,
        subject_digest=args.subject_digest,
        subject_entries=entries,
        receipt=receipt,
        trust_verdict=verdict,
    )

    prepared = (
        rollback_root.parent
        / f".{rollback_root.name}{SDK_ROLLBACK_PREPARED_SUFFIX}"
    )
    rollback_created = False
    if rollback_root.exists():
        rollback_validation = validate_live_canonical_root(
            rollback_root,
            required_files=required,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            subject_entries=entries,
            receipt=receipt,
            operator_change_ref=operator_change,
        )
    else:
        prepare_canonical_stage(
            prepared=prepared,
            target=rollback_root,
            store=absolute_existing_directory(
                args.subject_store,
                "subject store",
            ),
            required_files=required,
            entries=entries,
            verdict=verdict,
            receipt=receipt,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            authority=authority,
            observed_at=args.observed_at,
            live=True,
            operator_change_ref=operator_change,
        )
        rollback_manifest_path = (
            prepared / "manifest" / "federation_mirror_manifest.json"
        )
        rollback_manifest = read_json(
            rollback_manifest_path,
            "prepared SDK rollback manifest",
        )
        rollback_manifest["refresh_command"] = (
            "scripts/aoa-routing-cutover refresh-materialized "
            "--seal-sdk-rollback"
        )
        rollback_manifest["predecessor_rollback"][
            "operationally_required"
        ] = False
        write_json_atomic(rollback_manifest_path, rollback_manifest)
        validate_live_canonical_root(
            prepared,
            required_files=required,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            subject_entries=entries,
            receipt=receipt,
            operator_change_ref=operator_change,
        )
        os.replace(prepared, rollback_root)
        fsync_directory(rollback_root.parent)
        rollback_created = True
        rollback_validation = validate_live_canonical_root(
            rollback_root,
            required_files=required,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            subject_entries=entries,
            receipt=receipt,
            operator_change_ref=operator_change,
        )

    manifest = canonical_manifest(
        target_root=target,
        required_files=required,
        subject_entries=entries,
        trust_verdict=verdict,
        receipt=receipt,
        sdk_source_ref=args.sdk_source_ref,
        predecessor_source_ref=args.predecessor_source_ref,
        subject_digest=args.subject_digest,
        authority=authority,
        observed_at=args.observed_at or datetime.now(timezone.utc).isoformat(),
        activation_mode="authorized_live_cutover",
        operator_change_ref=operator_change,
    )
    manifest["refresh_command"] = (
        "scripts/aoa-routing-cutover refresh-materialized "
        "--explicit-exact-inputs"
    )
    manifest["sdk_runtime_rollback"] = sdk_runtime_rollback_binding(
        rollback_root=rollback_root,
        sdk_source_ref=args.sdk_source_ref,
        subject_digest=args.subject_digest,
    )
    manifest["predecessor_rollback"]["operationally_required"] = False
    write_json_atomic(
        target / "manifest" / "federation_mirror_manifest.json",
        manifest,
    )
    result = validate_live_canonical_root(
        target,
        required_files=required,
        sdk_source_ref=args.sdk_source_ref,
        predecessor_source_ref=args.predecessor_source_ref,
        subject_digest=args.subject_digest,
        subject_entries=entries,
        receipt=receipt,
        operator_change_ref=operator_change,
    )
    validate_sdk_runtime_rollback_binding(
        manifest.get("sdk_runtime_rollback"),
        sdk_source_ref=args.sdk_source_ref,
        subject_digest=args.subject_digest,
        rollback_root_name=rollback_root.name,
    )
    result.update(
        {
            "operation": "refresh-materialized",
            "refreshed": True,
            "idempotent_retry": not rollback_created
            and not source_inspection[
                "legacy_manifest_without_subject_ledger"
            ],
            "legacy_manifest_upgraded": source_inspection[
                "legacy_manifest_without_subject_ledger"
            ],
            "previous_manifest_digest": source_inspection[
                "previous_manifest_digest"
            ],
            "sdk_rollback_root": str(rollback_root),
            "sdk_rollback_created": rollback_created,
            "sdk_rollback_validation": rollback_validation,
            "predecessor_implementation_required": False,
            "predecessor_tree_mutated": False,
            "archive_authorized": False,
        }
    )
    return result


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    required, authority, entries, receipt, verdict = validate_inputs(args)
    target = absolute_runtime_path(args.target_root, "target root")
    store = absolute_existing_directory(args.subject_store, "subject store")
    live = bool(args.authorized_live_cutover)
    if live:
        ensure_live_target_shape(target)
        if not args.operator_change_ref:
            raise CutoverError(
                "authorized live cutover requires --operator-change-ref"
            )
        args.operator_change_ref = require_operator_change_ref(
            args.operator_change_ref
        )
    else:
        if is_live_target_shape(target):
            raise CutoverError(
                "a live-shaped routing target requires "
                "--authorized-live-cutover"
            )
        if args.operator_change_ref is not None:
            raise CutoverError(
                "isolated cutover must not accept --operator-change-ref"
            )
    rollback = (
        absolute_runtime_path(args.rollback_root, "rollback root")
        if args.rollback_root
        else None
    )
    prepared = target.parent / f".{target.name}{CANONICAL_PREPARED_SUFFIX}"
    if rollback is not None:
        if rollback == target or rollback in target.parents or target in rollback.parents:
            raise CutoverError("target and rollback roots must be disjoint")
        if rollback.parent != target.parent:
            raise CutoverError(
                "rollback root must share the target parent for atomic activation"
            )
    target.parent.mkdir(parents=True, exist_ok=True)

    if not live:
        if rollback is not None:
            raise CutoverError(
                "isolated canonical materialization must not set rollback root"
            )
        if target.exists():
            result = validate_canonical_root(
                target,
                required_files=required,
                sdk_source_ref=args.sdk_source_ref,
                predecessor_source_ref=args.predecessor_source_ref,
                subject_digest=args.subject_digest,
                subject_entries=entries,
                receipt=receipt,
            )
            result.update(
                {
                    "operation": "materialize",
                    "activated": True,
                    "idempotent_retry": True,
                    "retry_state": "already_materialized",
                    "rollback_root": None,
                    "predecessor_validation": None,
                }
            )
            return result
        prepare_canonical_stage(
            prepared=prepared,
            target=target,
            store=store,
            required_files=required,
            entries=entries,
            verdict=verdict,
            receipt=receipt,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            authority=authority,
            observed_at=args.observed_at,
            live=False,
            operator_change_ref=None,
        )
        os.replace(prepared, target)
        fsync_directory(target.parent)
        result = validate_canonical_root(
            target,
            required_files=required,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            subject_entries=entries,
            receipt=receipt,
        )
        result.update(
            {
                "operation": "materialize",
                "activated": True,
                "idempotent_retry": False,
                "retry_state": "fresh_isolated_materialization",
                "rollback_root": None,
                "predecessor_validation": None,
            }
        )
        return result

    assert rollback is not None
    operator_change = args.operator_change_ref
    assert isinstance(operator_change, str)
    initial = (
        target.is_dir()
        and not rollback.exists()
        and not prepared.exists()
    )
    prepared_before_swap = (
        target.is_dir()
        and not rollback.exists()
        and prepared.is_dir()
    )
    interrupted_between_swaps = (
        not target.exists()
        and rollback.is_dir()
        and prepared.is_dir()
    )
    already_activated = (
        target.is_dir()
        and rollback.is_dir()
        and not prepared.exists()
    )
    if not (
        initial
        or prepared_before_swap
        or interrupted_between_swaps
        or already_activated
    ):
        raise CutoverError(
            "live cutover roots do not match an initial, prepared, "
            "interrupted, or already-activated transaction state"
        )

    if already_activated:
        predecessor_inspection = validate_predecessor_root(
            rollback,
            required_files=required,
            predecessor_source_ref=args.predecessor_source_ref,
        )
        result = validate_live_canonical_root(
            target,
            required_files=required,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            subject_entries=entries,
            receipt=receipt,
            operator_change_ref=operator_change,
        )
        result.update(
            {
                "operation": "materialize",
                "activated": True,
                "idempotent_retry": True,
                "retry_state": "already_activated",
                "rollback_root": str(rollback),
                "predecessor_validation": predecessor_inspection,
            }
        )
        return result

    predecessor_root = (
        rollback if interrupted_between_swaps else target
    )
    predecessor_inspection = validate_predecessor_root(
        predecessor_root,
        required_files=required,
        predecessor_source_ref=args.predecessor_source_ref,
    )
    prepare_canonical_stage(
        prepared=prepared,
        target=target,
        store=store,
        required_files=required,
        entries=entries,
        verdict=verdict,
        receipt=receipt,
        sdk_source_ref=args.sdk_source_ref,
        predecessor_source_ref=args.predecessor_source_ref,
        subject_digest=args.subject_digest,
        authority=authority,
        observed_at=args.observed_at,
        live=True,
        operator_change_ref=operator_change,
    )

    retry_state = "continued_after_predecessor_rename"
    if not interrupted_between_swaps:
        os.replace(target, rollback)
        fsync_directory(target.parent)
        retry_state = (
            "continued_prepared_activation"
            if prepared_before_swap
            else "fresh_live_activation"
        )
    try:
        os.replace(prepared, target)
        fsync_directory(target.parent)
    except Exception:
        if not target.exists() and rollback.is_dir():
            os.replace(rollback, target)
            fsync_directory(target.parent)
        raise
    result = validate_live_canonical_root(
        target,
        required_files=required,
        sdk_source_ref=args.sdk_source_ref,
        predecessor_source_ref=args.predecessor_source_ref,
        subject_digest=args.subject_digest,
        subject_entries=entries,
        receipt=receipt,
        operator_change_ref=operator_change,
    )
    result.update(
        {
            "operation": "materialize",
            "activated": True,
            "idempotent_retry": False,
            "retry_state": retry_state,
            "rollback_root": str(rollback),
            "predecessor_validation": predecessor_inspection,
        }
    )
    return result


def check(args: argparse.Namespace) -> dict[str, Any]:
    required, _authority, entries, receipt, _verdict = validate_inputs(args)
    target = absolute_runtime_path(args.target_root, "target root")
    result = validate_canonical_root(
        target,
        required_files=required,
        sdk_source_ref=args.sdk_source_ref,
        predecessor_source_ref=args.predecessor_source_ref,
        subject_digest=args.subject_digest,
        subject_entries=entries,
        receipt=receipt,
    )
    result["operation"] = "check"
    return result


def validate_embedded_canonical_root(
    target: Path,
    *,
    required_files: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = read_json(
        target / "manifest" / "federation_mirror_manifest.json",
        "materialized routing manifest",
    )
    sdk_source_ref = require_git_object_id(
        str(manifest.get("source_git_commit") or ""),
        "materialized routing SDK source ref",
    )
    subject_digest = require_sha256_digest(
        str(manifest.get("artifact_subject_digest") or ""),
        "materialized routing subject digest",
    )
    predecessor = manifest.get("predecessor_rollback")
    predecessor_source_ref = require_git_object_id(
        str(
            predecessor.get("source_ref")
            if isinstance(predecessor, dict)
            else ""
        ),
        "materialized routing predecessor source ref",
    )
    receipt = manifest.get("owner_switch_receipt")
    if not isinstance(receipt, dict):
        raise CutoverError(
            "materialized routing owner-switch receipt is missing"
        )
    validate_owner_switch_receipt(
        receipt,
        sdk_source_ref=sdk_source_ref,
        predecessor_source_ref=predecessor_source_ref,
    )
    subject_entries = validate_embedded_subject_ledger(
        manifest.get("artifact_subject_ledger"),
        subject_digest=subject_digest,
    )
    result = validate_canonical_root(
        target,
        required_files=required_files,
        sdk_source_ref=sdk_source_ref,
        predecessor_source_ref=predecessor_source_ref,
        subject_digest=subject_digest,
        subject_entries=subject_entries,
        receipt=receipt,
    )
    return result, manifest


def inspect_materialized(args: argparse.Namespace) -> dict[str, Any]:
    """Verify current SDK-canonical bytes without reopening release admission.

    The exact-input ``check`` operation remains the authority for proving that
    a materialization matches its external subject store and trust inputs.
    This operation verifies only the integrity and embedded provenance of the
    already admitted runtime mirror so ordinary stack health checks never need
    an SDK or predecessor source checkout.
    """

    target = absolute_existing_directory(
        args.target_root,
        "materialized routing target root",
    )
    required = routing_required_files(
        absolute_existing_file(
            args.routing_config,
            "routing federation config",
        )
    )
    result, _manifest = validate_embedded_canonical_root(
        target,
        required_files=required,
    )
    result.update(
        {
            "operation": "inspect-materialized",
            "verification_scope": (
                "current_materialized_integrity_and_embedded_provenance"
            ),
            "external_release_admission_rechecked": False,
        }
    )
    return result


def inspect_active_canonical(
    target: Path,
    *,
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        manifest = read_json(
            target / "manifest" / "federation_mirror_manifest.json",
            "active canonical routing manifest",
        )
    except CanaryError as exc:
        return {"verified": False, "reasons": [str(exc)]}
    expected = {
        "routing_producer_posture": CANONICAL_POSTURE,
        "source_git_commit": sdk_source_ref,
        "artifact_subject_digest": subject_digest,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            reasons.append(f"active canonical routing field drifted: {key}")
    rollback = manifest.get("predecessor_rollback")
    if (
        not isinstance(rollback, dict)
        or rollback.get("source_ref") != predecessor_source_ref
    ):
        reasons.append("active canonical predecessor rollback ref drifted")
    try:
        require_canonical_authority(
            manifest.get("g5_authority"),
            "active canonical routing g5_authority",
        )
    except CutoverError as exc:
        reasons.append(str(exc))
    return {"verified": not reasons, "reasons": reasons}


def sdk_runtime_rollback_receipt(
    *,
    sdk_source_ref: str,
    subject_digest: str,
    operator_change_ref: str,
    replaced_target_inspection: dict[str, Any],
    restored_at: str,
) -> dict[str, Any]:
    return {
        "schema": SDK_RUNTIME_ROLLBACK_RECEIPT_SCHEMA,
        "state": "sdk_runtime_rollback_active",
        "sdk_source_ref": sdk_source_ref,
        "artifact_subject_digest": subject_digest,
        "operator_change_ref": operator_change_ref,
        "restored_at": restored_at,
        "source_owner_state": "sdk_canonical_unchanged",
        "predecessor_implementation_required": False,
        "archive_authorized": False,
        "replaced_target_inspection": replaced_target_inspection,
    }


def validate_sdk_runtime_rollback_receipt(
    value: Any,
    *,
    sdk_source_ref: str,
    subject_digest: str,
    operator_change_ref: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CutoverError("SDK runtime rollback receipt is missing")
    expected = {
        "schema": SDK_RUNTIME_ROLLBACK_RECEIPT_SCHEMA,
        "state": "sdk_runtime_rollback_active",
        "sdk_source_ref": sdk_source_ref,
        "artifact_subject_digest": subject_digest,
        "operator_change_ref": operator_change_ref,
        "source_owner_state": "sdk_canonical_unchanged",
        "predecessor_implementation_required": False,
        "archive_authorized": False,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise CutoverError(
                f"SDK runtime rollback receipt drifted: {key}"
            )
    if not isinstance(value.get("restored_at"), str) or not value["restored_at"]:
        raise CutoverError("SDK runtime rollback receipt time is missing")
    if not isinstance(value.get("replaced_target_inspection"), dict):
        raise CutoverError(
            "SDK runtime rollback replaced-target inspection is missing"
        )
    return dict(value)


def load_sdk_runtime_rollback_receipt(
    root: Path,
) -> dict[str, Any] | None:
    receipt_path = root / SDK_RUNTIME_ROLLBACK_REL
    if receipt_path.is_symlink():
        raise CutoverError(
            "SDK runtime rollback receipt must not be a symlink"
        )
    if not receipt_path.exists():
        return None
    return read_json(receipt_path, "SDK runtime rollback receipt")


def remove_exact_sdk_runtime_rollback_receipt(
    root: Path,
    *,
    expected_receipt: dict[str, Any],
) -> None:
    receipt_path = root / SDK_RUNTIME_ROLLBACK_REL
    if not receipt_path.exists():
        return
    persisted = read_json(receipt_path, "failed SDK runtime rollback receipt")
    if stable_digest(persisted) != stable_digest(expected_receipt):
        raise CutoverError(
            "failed SDK rollback receipt changed before cleanup"
        )
    receipt_path.unlink()
    fsync_directory(receipt_path.parent)


def inspect_embedded_canonical_for_rollback(
    root: Path,
    *,
    required_files: list[str],
) -> dict[str, Any]:
    try:
        result, manifest = validate_embedded_canonical_root(
            root,
            required_files=required_files,
        )
    except (CanaryError, OSError) as exc:
        return {"verified": False, "reasons": [str(exc)]}
    return {
        "verified": True,
        "reasons": [],
        "sdk_source_ref": result["sdk_source_ref"],
        "artifact_subject_digest": result["artifact_subject_digest"],
        "manifest_digest": stable_digest(manifest),
    }


def sdk_rollback_result(
    *,
    target: Path,
    retain_root: Path,
    operator_change_ref: str,
    restored_validation: dict[str, Any],
    replaced_target_inspection: dict[str, Any],
    receipt: dict[str, Any],
    retry_state: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "schema": "abyss_stack_routing_sdk_runtime_rollback_v1",
        "operation": "rollback-sdk",
        "restored": True,
        "idempotent_retry": retry_state == "already_restored",
        "retry_state": retry_state,
        "runtime_owner_state": "sdk_runtime_rollback_active",
        "source_owner_state": "sdk_canonical_unchanged",
        "target_root": str(target),
        "replaced_target_retain_root": str(retain_root),
        "sdk_source_ref": restored_validation["sdk_source_ref"],
        "artifact_subject_digest": restored_validation[
            "artifact_subject_digest"
        ],
        "operator_change_ref": operator_change_ref,
        "restored_validation": restored_validation,
        "replaced_target_inspection": replaced_target_inspection,
        "rollback_receipt": SDK_RUNTIME_ROLLBACK_REL,
        "rollback_receipt_digest": stable_digest(receipt),
        "predecessor_implementation_required": False,
        "predecessor_tree_used": False,
        "archive_authorized": False,
    }


def rollback_sdk(args: argparse.Namespace) -> dict[str, Any]:
    if not args.authorized_live_cutover:
        raise CutoverError("SDK rollback requires --authorized-live-cutover")
    operator_change = require_operator_change_ref(args.operator_change_ref)
    config = absolute_existing_file(args.routing_config, "routing config")
    required = routing_required_files(config)
    target = absolute_runtime_path(args.target_root, "target root")
    ensure_live_target_shape(target)
    rollback_root = absolute_runtime_path(
        args.sdk_rollback_root,
        "SDK rollback root",
    )
    retain_root = absolute_runtime_path(
        args.replaced_target_retain_root,
        "replaced target retain root",
    )
    roots = {target, rollback_root, retain_root}
    if len(roots) != 3 or any(
        left in right.parents or right in left.parents
        for left in roots
        for right in roots
        if left != right
    ):
        raise CutoverError(
            "target, SDK rollback, and retain roots must be disjoint"
        )
    if not (target.parent == rollback_root.parent == retain_root.parent):
        raise CutoverError(
            "SDK rollback roots must share one parent for atomic restore"
        )

    initial_state = (
        target.is_dir()
        and rollback_root.is_dir()
        and not retain_root.exists()
    )
    interrupted_between_swaps = (
        not target.exists()
        and rollback_root.is_dir()
        and retain_root.is_dir()
    )
    already_restored = (
        target.is_dir()
        and not rollback_root.exists()
        and retain_root.is_dir()
    )
    if not (
        initial_state
        or interrupted_between_swaps
        or already_restored
    ):
        raise CutoverError(
            "SDK rollback roots do not match an initial, interrupted, or "
            "already-restored transaction state"
        )

    if already_restored:
        restored_validation, _manifest = validate_embedded_canonical_root(
            target,
            required_files=required,
        )
        completed_receipt = load_sdk_runtime_rollback_receipt(target)
        validate_sdk_runtime_rollback_receipt(
            completed_receipt,
            sdk_source_ref=restored_validation["sdk_source_ref"],
            subject_digest=restored_validation["artifact_subject_digest"],
            operator_change_ref=operator_change,
        )
        replaced_inspection = inspect_embedded_canonical_for_rollback(
            retain_root,
            required_files=required,
        )
        assert completed_receipt is not None
        return sdk_rollback_result(
            target=target,
            retain_root=retain_root,
            operator_change_ref=operator_change,
            restored_validation=restored_validation,
            replaced_target_inspection=replaced_inspection,
            receipt=completed_receipt,
            retry_state="already_restored",
        )

    restored_validation, _manifest = validate_embedded_canonical_root(
        rollback_root,
        required_files=required,
    )
    staged_receipt = load_sdk_runtime_rollback_receipt(rollback_root)
    if interrupted_between_swaps:
        staged_receipt = validate_sdk_runtime_rollback_receipt(
            staged_receipt,
            sdk_source_ref=restored_validation["sdk_source_ref"],
            subject_digest=restored_validation["artifact_subject_digest"],
            operator_change_ref=operator_change,
        )
        replaced_inspection = inspect_embedded_canonical_for_rollback(
            retain_root,
            required_files=required,
        )
        try:
            os.replace(rollback_root, target)
            fsync_directory(target.parent)
        except Exception:
            if not target.exists():
                os.replace(retain_root, target)
                fsync_directory(target.parent)
                remove_exact_sdk_runtime_rollback_receipt(
                    rollback_root,
                    expected_receipt=staged_receipt,
                )
            raise
        return sdk_rollback_result(
            target=target,
            retain_root=retain_root,
            operator_change_ref=operator_change,
            restored_validation=restored_validation,
            replaced_target_inspection=replaced_inspection,
            receipt=staged_receipt,
            retry_state="continued_after_first_swap",
        )

    active_manifest = read_json(
        target / "manifest" / "federation_mirror_manifest.json",
        "active SDK routing manifest",
    )
    validate_sdk_runtime_rollback_binding(
        active_manifest.get("sdk_runtime_rollback"),
        sdk_source_ref=restored_validation["sdk_source_ref"],
        subject_digest=restored_validation["artifact_subject_digest"],
        rollback_root_name=rollback_root.name,
    )
    replaced_inspection = inspect_embedded_canonical_for_rollback(
        target,
        required_files=required,
    )
    if staged_receipt is not None:
        persisted_receipt = validate_sdk_runtime_rollback_receipt(
            staged_receipt,
            sdk_source_ref=restored_validation["sdk_source_ref"],
            subject_digest=restored_validation["artifact_subject_digest"],
            operator_change_ref=operator_change,
        )
        if persisted_receipt["replaced_target_inspection"] != (
            replaced_inspection
        ):
            raise CutoverError(
                "staged SDK rollback receipt no longer matches active target"
            )
    else:
        receipt = sdk_runtime_rollback_receipt(
            sdk_source_ref=restored_validation["sdk_source_ref"],
            subject_digest=restored_validation["artifact_subject_digest"],
            operator_change_ref=operator_change,
            replaced_target_inspection=replaced_inspection,
            restored_at=datetime.now(timezone.utc).isoformat(),
        )
        write_json_atomic(
            rollback_root / SDK_RUNTIME_ROLLBACK_REL,
            receipt,
        )
        persisted_receipt = load_sdk_runtime_rollback_receipt(rollback_root)
        persisted_receipt = validate_sdk_runtime_rollback_receipt(
            persisted_receipt,
            sdk_source_ref=restored_validation["sdk_source_ref"],
            subject_digest=restored_validation["artifact_subject_digest"],
            operator_change_ref=operator_change,
        )
    target_moved = False
    try:
        os.replace(target, retain_root)
        target_moved = True
        fsync_directory(target.parent)
        try:
            os.replace(rollback_root, target)
            fsync_directory(target.parent)
        except Exception:
            if not target.exists():
                os.replace(retain_root, target)
                target_moved = False
                fsync_directory(target.parent)
            raise
    except Exception:
        if target_moved and not target.exists() and retain_root.is_dir():
            os.replace(retain_root, target)
            fsync_directory(target.parent)
        remove_exact_sdk_runtime_rollback_receipt(
            rollback_root,
            expected_receipt=persisted_receipt,
        )
        raise
    restored_validation, _manifest = validate_embedded_canonical_root(
        target,
        required_files=required,
    )
    return sdk_rollback_result(
        target=target,
        retain_root=retain_root,
        operator_change_ref=operator_change,
        restored_validation=restored_validation,
        replaced_target_inspection=replaced_inspection,
        receipt=persisted_receipt,
        retry_state="fresh_restore",
    )


def remove_exact_compatibility_marker(
    rollback_root: Path,
    *,
    expected_marker: dict[str, Any],
) -> None:
    marker_path = rollback_root / COMPATIBILITY_ROLLBACK_REL
    if not marker_path.exists():
        return
    persisted = read_json(
        marker_path,
        "failed compatibility rollback marker",
    )
    if stable_digest(persisted) != stable_digest(expected_marker):
        raise CutoverError(
            "failed rollback marker changed before cleanup; refusing "
            "to remove unverified state"
        )
    marker_path.unlink()
    fsync_directory(marker_path.parent)


def load_staged_compatibility_marker(
    rollback_root: Path,
) -> dict[str, Any] | None:
    marker_path = rollback_root / COMPATIBILITY_ROLLBACK_REL
    if marker_path.is_symlink():
        raise CutoverError(
            "staged compatibility rollback marker must not be a symlink"
        )
    if not marker_path.exists():
        return None
    return read_json(
        marker_path,
        "staged compatibility rollback marker",
    )


def write_compatibility_marker_atomic(
    rollback_root: Path,
    marker: dict[str, Any],
) -> dict[str, Any]:
    marker_path = rollback_root / COMPATIBILITY_ROLLBACK_REL
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{marker_path.name}.stage-",
        dir=marker_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        write_json(temporary_path, marker)
        fsync_file(temporary_path)
        staged = read_json(
            temporary_path,
            "staged compatibility rollback marker",
        )
        if stable_digest(staged) != stable_digest(marker):
            raise CutoverError(
                "staged compatibility rollback marker digest drifted"
            )
        os.replace(temporary_path, marker_path)
        fsync_directory(marker_path.parent)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    persisted = read_json(
        marker_path,
        "compatibility rollback marker",
    )
    if stable_digest(persisted) != stable_digest(marker):
        raise CutoverError(
            "persisted compatibility rollback marker digest drifted"
        )
    return persisted


def validate_marked_predecessor(
    root: Path,
    *,
    marker: dict[str, Any],
    required_files: list[str],
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    operator_change_ref: str,
) -> dict[str, Any]:
    inspection = validate_predecessor_root(
        root,
        required_files=required_files,
        predecessor_source_ref=predecessor_source_ref,
        allow_compatibility_marker=True,
    )
    validate_compatibility_rollback_marker(
        marker,
        sdk_source_ref=sdk_source_ref,
        predecessor_source_ref=predecessor_source_ref,
        subject_digest=subject_digest,
        operator_change_ref=operator_change_ref,
        predecessor_inspection=inspection,
    )
    return inspection


def rollback_result(
    *,
    sdk_source_ref: str,
    subject_digest: str,
    operator_change_ref: str,
    target: Path,
    retain_root: Path,
    canonical_inspection: dict[str, Any],
    predecessor_inspection: dict[str, Any],
    persisted_marker: dict[str, Any],
    retry_state: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "schema": "abyss_stack_routing_g5_cutover_rollback_v1",
        "operation": "rollback",
        "restored": True,
        "idempotent_retry": retry_state == "already_restored",
        "retry_state": retry_state,
        "runtime_owner_state": "compatibility_rollback_active",
        "source_owner_state": "sdk_canonical_unchanged",
        "sdk_source_ref": sdk_source_ref,
        "target_root": str(target),
        "canonical_retain_root": str(retain_root),
        "artifact_subject_digest": subject_digest,
        "operator_change_ref": operator_change_ref,
        "canonical_identity_inspection": canonical_inspection,
        "predecessor_identity_inspection": predecessor_inspection,
        "compatibility_rollback_marker": COMPATIBILITY_ROLLBACK_REL,
        "compatibility_rollback_marker_digest": stable_digest(
            persisted_marker
        ),
        "archive_authorized": False,
    }


def rollback(args: argparse.Namespace) -> dict[str, Any]:
    sdk_ref = require_git_object_id(args.sdk_source_ref, "SDK source ref")
    predecessor_ref = require_git_object_id(
        args.predecessor_source_ref,
        "predecessor source ref",
    )
    digest = require_sha256_digest(args.subject_digest, "subject digest")
    operator_change = require_operator_change_ref(args.operator_change_ref)
    config = absolute_existing_file(args.routing_config, "routing config")
    required = routing_required_files(config)
    target = absolute_runtime_path(args.target_root, "target root")
    ensure_live_target_shape(target)
    rollback_root = absolute_runtime_path(args.rollback_root, "rollback root")
    retain_root = absolute_runtime_path(
        args.canonical_retain_root,
        "canonical retain root",
    )
    roots = {target, rollback_root, retain_root}
    if len(roots) != 3 or any(
        left in right.parents or right in left.parents
        for left in roots
        for right in roots
        if left != right
    ):
        raise CutoverError(
            "target, rollback, and canonical-retain roots must be disjoint"
        )
    if not (target.parent == rollback_root.parent == retain_root.parent):
        raise CutoverError("rollback roots must share one parent for atomic restore")

    initial_state = (
        target.is_dir()
        and rollback_root.is_dir()
        and not retain_root.exists()
    )
    interrupted_between_swaps = (
        not target.exists()
        and rollback_root.is_dir()
        and retain_root.is_dir()
    )
    already_restored = (
        target.is_dir()
        and not rollback_root.exists()
        and retain_root.is_dir()
    )
    if not (
        initial_state
        or interrupted_between_swaps
        or already_restored
    ):
        raise CutoverError(
            "rollback roots do not match an initial, interrupted, or "
            "already-restored transaction state"
        )

    if already_restored:
        completed_marker = load_staged_compatibility_marker(target)
        if completed_marker is None:
            raise CutoverError(
                "already-restored target lacks its compatibility marker"
            )
        predecessor_inspection = validate_marked_predecessor(
            target,
            marker=completed_marker,
            required_files=required,
            sdk_source_ref=sdk_ref,
            predecessor_source_ref=predecessor_ref,
            subject_digest=digest,
            operator_change_ref=operator_change,
        )
        canonical_inspection = inspect_active_canonical(
            retain_root,
            sdk_source_ref=sdk_ref,
            predecessor_source_ref=predecessor_ref,
            subject_digest=digest,
        )
        return rollback_result(
            sdk_source_ref=sdk_ref,
            subject_digest=digest,
            operator_change_ref=operator_change,
            target=target,
            retain_root=retain_root,
            canonical_inspection=canonical_inspection,
            predecessor_inspection=predecessor_inspection,
            persisted_marker=completed_marker,
            retry_state="already_restored",
        )

    staged_marker = load_staged_compatibility_marker(rollback_root)
    if interrupted_between_swaps:
        if staged_marker is None:
            raise CutoverError(
                "interrupted rollback tree lacks its exact staged marker"
            )
        predecessor_inspection = validate_marked_predecessor(
            rollback_root,
            marker=staged_marker,
            required_files=required,
            sdk_source_ref=sdk_ref,
            predecessor_source_ref=predecessor_ref,
            subject_digest=digest,
            operator_change_ref=operator_change,
        )
        canonical_inspection = inspect_active_canonical(
            retain_root,
            sdk_source_ref=sdk_ref,
            predecessor_source_ref=predecessor_ref,
            subject_digest=digest,
        )
        try:
            os.replace(rollback_root, target)
            fsync_directory(target.parent)
        except Exception:
            if not target.exists():
                os.replace(retain_root, target)
                fsync_directory(target.parent)
                remove_exact_compatibility_marker(
                    rollback_root,
                    expected_marker=staged_marker,
                )
            raise
        return rollback_result(
            sdk_source_ref=sdk_ref,
            subject_digest=digest,
            operator_change_ref=operator_change,
            target=target,
            retain_root=retain_root,
            canonical_inspection=canonical_inspection,
            predecessor_inspection=predecessor_inspection,
            persisted_marker=staged_marker,
            retry_state="continued_after_first_swap",
        )

    if (
        (target / COMPATIBILITY_ROLLBACK_REL).exists()
        or (target / COMPATIBILITY_ROLLBACK_REL).is_symlink()
    ):
        raise CutoverError(
            "initial live target already carries a compatibility marker"
        )
    inspection = inspect_active_canonical(
        target,
        sdk_source_ref=sdk_ref,
        predecessor_source_ref=predecessor_ref,
        subject_digest=digest,
    )
    predecessor_inspection = validate_predecessor_root(
        rollback_root,
        required_files=required,
        predecessor_source_ref=predecessor_ref,
        allow_compatibility_marker=staged_marker is not None,
    )
    if staged_marker is not None:
        predecessor_inspection = validate_marked_predecessor(
            rollback_root,
            marker=staged_marker,
            required_files=required,
            sdk_source_ref=sdk_ref,
            predecessor_source_ref=predecessor_ref,
            subject_digest=digest,
            operator_change_ref=operator_change,
        )
        remove_exact_compatibility_marker(
            rollback_root,
            expected_marker=staged_marker,
        )
    marker = compatibility_rollback_marker(
        sdk_source_ref=sdk_ref,
        predecessor_source_ref=predecessor_ref,
        subject_digest=digest,
        operator_change_ref=operator_change,
        predecessor_inspection=predecessor_inspection,
        rolled_back_at=datetime.now(timezone.utc).isoformat(),
    )
    persisted_marker = write_compatibility_marker_atomic(
        rollback_root,
        marker,
    )
    validate_compatibility_rollback_marker(
        persisted_marker,
        sdk_source_ref=sdk_ref,
        predecessor_source_ref=predecessor_ref,
        subject_digest=digest,
        operator_change_ref=operator_change,
        predecessor_inspection=predecessor_inspection,
    )
    canonical_moved = False
    try:
        os.replace(target, retain_root)
        canonical_moved = True
        fsync_directory(target.parent)
        try:
            os.replace(rollback_root, target)
            fsync_directory(target.parent)
        except Exception:
            if not target.exists():
                os.replace(retain_root, target)
                canonical_moved = False
                fsync_directory(target.parent)
            raise
    except Exception:
        if (
            canonical_moved
            and not target.exists()
            and retain_root.is_dir()
        ):
            os.replace(retain_root, target)
            canonical_moved = False
            fsync_directory(target.parent)
        remove_exact_compatibility_marker(
            rollback_root,
            expected_marker=persisted_marker,
        )
        raise
    return rollback_result(
        sdk_source_ref=sdk_ref,
        subject_digest=digest,
        operator_change_ref=operator_change,
        target=target,
        retain_root=retain_root,
        canonical_inspection=inspection,
        predecessor_inspection=predecessor_inspection,
        persisted_marker=persisted_marker,
        retry_state="fresh_restore",
    )


def add_exact_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--subject-store", required=True)
    parser.add_argument("--trust-verdict", required=True)
    parser.add_argument("--owner-switch-receipt", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--sdk-source-ref", required=True)
    parser.add_argument("--predecessor-source-ref", required=True)
    parser.add_argument("--subject-digest", required=True)
    parser.add_argument("--routing-config", default=str(DEFAULT_ROUTING_CONFIG))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize or verify receipt-bound canonical SDK routing bytes."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    materialize_parser = subparsers.add_parser("materialize")
    add_exact_input_args(materialize_parser)
    mode = materialize_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--isolated", action="store_true")
    mode.add_argument("--authorized-live-cutover", action="store_true")
    materialize_parser.add_argument("--rollback-root")
    materialize_parser.add_argument("--observed-at")
    materialize_parser.add_argument("--operator-change-ref")
    materialize_parser.set_defaults(handler=materialize)

    refresh_parser = subparsers.add_parser("refresh-materialized")
    add_exact_input_args(refresh_parser)
    refresh_parser.add_argument(
        "--authorized-live-cutover",
        action="store_true",
        required=True,
    )
    refresh_parser.add_argument("--sdk-rollback-root", required=True)
    refresh_parser.add_argument("--observed-at")
    refresh_parser.add_argument("--operator-change-ref", required=True)
    refresh_parser.set_defaults(handler=refresh_materialized)

    check_parser = subparsers.add_parser("check")
    add_exact_input_args(check_parser)
    check_parser.set_defaults(handler=check)

    inspect_parser = subparsers.add_parser("inspect-materialized")
    inspect_parser.add_argument("--target-root", required=True)
    inspect_parser.add_argument(
        "--routing-config",
        default=str(DEFAULT_ROUTING_CONFIG),
    )
    inspect_parser.set_defaults(handler=inspect_materialized)

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument(
        "--authorized-live-cutover",
        action="store_true",
        required=True,
    )
    rollback_parser.add_argument("--target-root", required=True)
    rollback_parser.add_argument("--rollback-root", required=True)
    rollback_parser.add_argument("--canonical-retain-root", required=True)
    rollback_parser.add_argument("--sdk-source-ref", required=True)
    rollback_parser.add_argument("--predecessor-source-ref", required=True)
    rollback_parser.add_argument("--subject-digest", required=True)
    rollback_parser.add_argument("--operator-change-ref", required=True)
    rollback_parser.add_argument(
        "--routing-config",
        default=str(DEFAULT_ROUTING_CONFIG),
    )
    rollback_parser.set_defaults(handler=rollback)

    sdk_rollback_parser = subparsers.add_parser("rollback-sdk")
    sdk_rollback_parser.add_argument(
        "--authorized-live-cutover",
        action="store_true",
        required=True,
    )
    sdk_rollback_parser.add_argument("--target-root", required=True)
    sdk_rollback_parser.add_argument("--sdk-rollback-root", required=True)
    sdk_rollback_parser.add_argument(
        "--replaced-target-retain-root",
        required=True,
    )
    sdk_rollback_parser.add_argument("--operator-change-ref", required=True)
    sdk_rollback_parser.add_argument(
        "--routing-config",
        default=str(DEFAULT_ROUTING_CONFIG),
    )
    sdk_rollback_parser.set_defaults(handler=rollback_sdk)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.handler(args)
    except (CanaryError, OSError) as exc:
        payload = {
            "ok": False,
            "schema": "abyss_stack_routing_g5_cutover_error_v1",
            "operation": args.command,
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
