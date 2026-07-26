#!/usr/bin/env python3
"""Fail-closed intake for the receipt-bound canonical SDK routing producer.

This is deliberately separate from the non-canonical canary adapter.  It can
materialize SDK routing bytes as the live runtime mirror only when the exact
public-release trust verdict, subject store, owner-switch receipt, rollback
root, and operator change record agree.
"""

from __future__ import annotations

import argparse
import hashlib
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
    stable_digest,
    validate_subject_store,
    write_json,
)


CANONICAL_POSTURE = "sdk_canonical"
OWNER_SWITCH_RECEIPT_SCHEMA = "aoa_sdk_routing_g5_owner_switch_receipt_v1"
OWNER_SWITCH_RECEIPT_REL = "succession/routing-g5-owner-switch.json"
CANONICAL_PROFILE_ID = "aoa-sdk-g5-canonical"
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
    if "abyss-stack:routing-canonical" not in record.get("consumer_refs", []):
        raise CutoverError("canonical trust record lacks runtime consumer admission")
    if set(record.get("required_controls", [])) != EXPECTED_CONTROLS:
        raise CutoverError("canonical trust record required controls drifted")
    if set(record.get("verified_controls", [])) != EXPECTED_CONTROLS:
        raise CutoverError("canonical trust record verified controls drifted")
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
    if "runtime" not in admission.get("allowed_consumer_intents", []):
        raise CutoverError("canonical producer admission does not allow runtime")
    if set(admission.get("required_controls", [])) != EXPECTED_CONTROLS:
        raise CutoverError("canonical producer admission controls drifted")
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
    }


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
    if target.exists() and rollback is None:
        raise CutoverError("replacing an existing target requires --rollback-root")
    if live and (not target.is_dir() or rollback is None):
        raise CutoverError(
            "authorized live cutover requires an existing target and --rollback-root"
        )
    if rollback is not None:
        if rollback.exists():
            raise CutoverError(f"rollback root already exists: {rollback}")
        if rollback == target or rollback in target.parents or target in rollback.parents:
            raise CutoverError("target and rollback roots must be disjoint")
        if rollback.parent != target.parent:
            raise CutoverError(
                "rollback root must share the target parent for atomic activation"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.sdk-canonical-stage-",
            dir=target.parent,
        )
    )
    activated = False
    rolled_aside = False
    try:
        for relative in required:
            source = resolved_subject_file(store, relative)
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if file_digest_hex(destination) != entries[relative].get("sha256_hex"):
                raise CutoverError(
                    "copied canonical file does not match subject ledger: "
                    f"{relative}"
                )
        observed_at = args.observed_at or datetime.now(timezone.utc).isoformat()
        manifest = canonical_manifest(
            target_root=stage,
            required_files=required,
            trust_verdict=verdict,
            receipt=receipt,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            authority=authority,
            observed_at=observed_at,
            activation_mode="authorized_live_cutover" if live else "isolated",
            operator_change_ref=args.operator_change_ref if live else None,
        )
        write_json(stage / "manifest" / "federation_mirror_manifest.json", manifest)
        validate_canonical_root(
            stage,
            required_files=required,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            subject_entries=entries,
            receipt=receipt,
        )
        if target.exists():
            assert rollback is not None
            os.replace(target, rollback)
            rolled_aside = True
        try:
            os.replace(stage, target)
            activated = True
        except Exception:
            if rolled_aside and rollback is not None and not target.exists():
                os.replace(rollback, target)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
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
            "activated": activated,
            "rollback_root": str(rollback) if rollback is not None else None,
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


def rollback(args: argparse.Namespace) -> dict[str, Any]:
    sdk_ref = require_git_object_id(args.sdk_source_ref, "SDK source ref")
    predecessor_ref = require_git_object_id(
        args.predecessor_source_ref,
        "predecessor source ref",
    )
    digest = require_sha256_digest(args.subject_digest, "subject digest")
    operator_change = require_operator_change_ref(args.operator_change_ref)
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
    if not target.is_dir() or not rollback_root.is_dir():
        raise CutoverError("rollback requires active canonical and rollback roots")
    if retain_root.exists():
        raise CutoverError(f"canonical retain root already exists: {retain_root}")
    if not (target.parent == rollback_root.parent == retain_root.parent):
        raise CutoverError("rollback roots must share one parent for atomic restore")
    inspection = inspect_active_canonical(
        target,
        sdk_source_ref=sdk_ref,
        predecessor_source_ref=predecessor_ref,
        subject_digest=digest,
    )
    os.replace(target, retain_root)
    try:
        os.replace(rollback_root, target)
    except Exception:
        os.replace(retain_root, target)
        raise
    return {
        "ok": True,
        "schema": "abyss_stack_routing_g5_cutover_rollback_v1",
        "operation": "rollback",
        "restored": True,
        "runtime_owner_state": "compatibility_rollback_active",
        "source_owner_state": "sdk_canonical_unchanged",
        "target_root": str(target),
        "canonical_retain_root": str(retain_root),
        "artifact_subject_digest": digest,
        "operator_change_ref": operator_change,
        "canonical_identity_inspection": inspection,
        "archive_authorized": False,
    }


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

    check_parser = subparsers.add_parser("check")
    add_exact_input_args(check_parser)
    check_parser.set_defaults(handler=check)

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
    rollback_parser.set_defaults(handler=rollback)
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
