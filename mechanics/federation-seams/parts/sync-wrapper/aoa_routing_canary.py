#!/usr/bin/env python3
"""Fail-closed materialization of an exact SDK routing canary.

This command is a runtime-consumer adapter.  It does not authorize the G5
producer switch and it never treats the canary as canonical routing authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ROUTING_CONFIG = (
    REPO_ROOT / "config-templates" / "Configs" / "federation" / "aoa-routing.yaml"
)
ARTIFACT_CLASS = "thin_routing_readmodel_bundle"
ABI_EPOCH = "aoa_routing_thin_router_v1"
CANARY_POSTURE = "sdk_g5_candidate_canary"
EXPECTED_CONTROLS = {"abi_signature", "sbom", "slsa_in_toto"}
G5_AUTHORITY_FLAGS = {
    "archive_authorized",
    "canonical_producer_switch_authorized",
    "compatibility_window_started",
    "live_runtime_mutation_authorized",
    "predecessor_maintenance_only",
    "sdk_canonical",
}


class CanaryError(ValueError):
    """An input or runtime state failed the canary contract."""


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CanaryError(f"{label} is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CanaryError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CanaryError(f"{label} must be a JSON object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def stable_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_digest_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_git_object_id(value: str, label: str) -> str:
    if len(value) not in {40, 64} or any(ch not in "0123456789abcdef" for ch in value):
        raise CanaryError(f"{label} must be a lowercase 40- or 64-hex Git object id")
    return value


def require_sha256_digest(value: str, label: str) -> str:
    if (
        not value.startswith("sha256:")
        or len(value) != 71
        or any(ch not in "0123456789abcdef" for ch in value[7:])
    ):
        raise CanaryError(f"{label} must be a sha256 digest")
    return value


def safe_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise CanaryError(f"{label} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CanaryError(f"{label} must stay below its declared root: {value!r}")
    return path.as_posix()


def absolute_runtime_path(value: str, label: str) -> Path:
    raw = Path(value)
    if not raw.is_absolute():
        raise CanaryError(f"{label} must be an absolute path")
    if raw.is_symlink():
        raise CanaryError(f"{label} must not be a symlink")
    path = raw.resolve(strict=False)
    if path == Path("/") or len(path.parts) < 4:
        raise CanaryError(f"{label} is too broad for canary mutation: {path}")
    return path


def require_operator_change_ref(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CanaryError("operator change ref must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > 256 or any(ord(ch) < 32 for ch in normalized):
        raise CanaryError("operator change ref contains unsupported characters")
    return normalized


def routing_required_files(config_path: Path) -> list[str]:
    """Read the simple, source-owned required_files YAML sequence stdlib-only."""

    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise CanaryError(f"routing config is missing: {config_path}") from exc

    layer_seen = False
    in_required = False
    required: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped == "layer: aoa-routing":
            layer_seen = True
        if raw.startswith("required_files:"):
            in_required = True
            continue
        if not in_required:
            continue
        if raw.startswith("  - "):
            required.append(
                safe_relative_path(raw.removeprefix("  - ").strip(), "required_files entry")
            )
            continue
        if stripped and not raw.startswith((" ", "\t", "#")):
            break
    if not layer_seen or not required:
        raise CanaryError(
            f"routing config must declare layer aoa-routing and required_files: {config_path}"
        )
    if len(required) != len(set(required)):
        raise CanaryError("routing config required_files contains duplicates")
    return required


def resolved_subject_file(subject_root: Path, relative: str) -> Path:
    root = subject_root.resolve(strict=True)
    candidate = subject_root / relative
    if candidate.is_symlink():
        raise CanaryError(f"subject-store file must not be a symlink: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise CanaryError(f"subject-store file is missing or escapes its root: {relative}") from exc
    if not resolved.is_file():
        raise CanaryError(f"subject-store entry is not a file: {relative}")
    return resolved


def validate_subject_store(
    subject_root: Path,
    *,
    required_files: list[str],
    subject_digest: str,
    consumer_intent: str = "runtime_canary",
) -> dict[str, dict[str, Any]]:
    metadata = read_json(subject_root / "subject-store.json", "subject-store metadata")
    if metadata.get("schema") != "abyss_machine_artifact_subject_store_v1":
        raise CanaryError("subject-store schema is invalid")
    if metadata.get("artifact_class") != ARTIFACT_CLASS:
        raise CanaryError("subject-store artifact class is invalid")
    if metadata.get("owner_repo") != "aoa-sdk":
        raise CanaryError("subject-store owner must be aoa-sdk")
    if metadata.get("aggregate_digest") != subject_digest:
        raise CanaryError("subject-store aggregate digest drifted")
    if metadata.get("consumer_intent") != consumer_intent:
        raise CanaryError(
            "subject-store consumer intent must be "
            f"{consumer_intent}"
        )

    raw_files = metadata.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise CanaryError("subject-store files are missing")
    if stable_digest(raw_files) != subject_digest:
        raise CanaryError("subject-store aggregate digest does not match its file ledger")

    by_path: dict[str, dict[str, Any]] = {}
    for index, raw_entry in enumerate(raw_files):
        if not isinstance(raw_entry, dict):
            raise CanaryError(f"subject-store files[{index}] must be an object")
        relative = safe_relative_path(
            raw_entry.get("path"),
            f"subject-store files[{index}].path",
        )
        if relative in by_path:
            raise CanaryError(f"subject-store has a duplicate file entry: {relative}")
        expected = require_sha256_digest(
            str(raw_entry.get("sha256") or ""),
            f"subject-store digest for {relative}",
        )
        source = resolved_subject_file(subject_root, relative)
        actual_hex = file_digest_hex(source)
        if expected != f"sha256:{actual_hex}":
            raise CanaryError(f"subject-store file digest drifted: {relative}")
        if raw_entry.get("sha256_hex") != actual_hex:
            raise CanaryError(f"subject-store hex digest drifted: {relative}")
        if raw_entry.get("bytes") != source.stat().st_size:
            raise CanaryError(f"subject-store byte count drifted: {relative}")
        by_path[relative] = raw_entry

    missing = [relative for relative in required_files if relative not in by_path]
    if missing:
        raise CanaryError(
            "subject-store lacks route-api required files: " + ", ".join(missing)
        )
    return by_path


def require_false_authority_flags(value: Any, label: str) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise CanaryError(f"{label} must be an object")
    missing = sorted(G5_AUTHORITY_FLAGS - set(value))
    if missing:
        raise CanaryError(f"{label} lacks flags: {', '.join(missing)}")
    asserted = sorted(key for key in G5_AUTHORITY_FLAGS if value.get(key) is not False)
    if asserted:
        raise CanaryError(f"{label} asserts forbidden authority: {', '.join(asserted)}")
    return {key: False for key in sorted(G5_AUTHORITY_FLAGS)}


def validate_trust_verdict(
    verdict: dict[str, Any],
    *,
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
) -> dict[str, bool]:
    if verdict.get("schema") != "abyss_machine_artifact_trust_gate_v1":
        raise CanaryError("trust verdict schema is invalid")
    if verdict.get("ok") is not True or verdict.get("verdict") not in {"allow", "warn"}:
        raise CanaryError("trust verdict does not admit the canary")
    if verdict.get("artifact_class") != ARTIFACT_CLASS:
        raise CanaryError("trust verdict artifact class is invalid")
    if verdict.get("consumer_intent") != "runtime_canary":
        raise CanaryError("trust verdict consumer intent must be runtime_canary")
    if verdict.get("subject_digest") != subject_digest:
        raise CanaryError("trust verdict subject digest drifted")
    record_id = verdict.get("record_id")
    if not isinstance(record_id, str) or not record_id:
        raise CanaryError("trust verdict record id is missing")
    if verdict.get("require_latest") is not True or verdict.get("latest_record_id") != record_id:
        raise CanaryError("trust verdict is not bound to the latest record")
    if verdict.get("reasons") or verdict.get("blockers"):
        raise CanaryError("trust verdict contains admission reasons or blockers")

    decision = verdict.get("decision")
    if (
        not isinstance(decision, dict)
        or decision.get("model") != "fail_closed_consumer_admission"
        or decision.get("allow") is not True
        or decision.get("consumer_intent") != "runtime_canary"
    ):
        raise CanaryError("trust verdict decision is not fail-closed canary admission")

    record = verdict.get("record")
    if not isinstance(record, dict):
        raise CanaryError("trust verdict record is missing")
    if record.get("record_id") != record_id or record.get("artifact_class") != ARTIFACT_CLASS:
        raise CanaryError("trust verdict record identity drifted")
    if record.get("source_repo") != "aoa-sdk" or record.get("source_ref") != sdk_source_ref:
        raise CanaryError("trust verdict record is not bound to the exact aoa-sdk source")
    if record.get("artifact_subjects_digest") != subject_digest:
        raise CanaryError("trust verdict record subject digest drifted")
    if record.get("lifecycle_state") != "manually-verified":
        raise CanaryError("trust verdict record lifecycle is not manually-verified")
    if record.get("latest_eligible") is not True or record.get("terminal_state") is not False:
        raise CanaryError("trust verdict record is not latest-eligible and non-terminal")
    if record.get("verification_ok") is not True:
        raise CanaryError("trust verdict record verification is not green")
    if "abyss-stack:routing-canary" not in record.get("consumer_refs", []):
        raise CanaryError("trust verdict record does not admit abyss-stack:routing-canary")
    if set(record.get("required_controls", [])) != EXPECTED_CONTROLS:
        raise CanaryError("trust verdict required controls drifted")
    if set(record.get("verified_controls", [])) != EXPECTED_CONTROLS:
        raise CanaryError("trust verdict verified controls drifted")
    subject_store = record.get("artifact_subject_store")
    if (
        not isinstance(subject_store, dict)
        or subject_store.get("required") is not True
        or subject_store.get("ok") is not True
        or subject_store.get("aggregate_digest") != subject_digest
    ):
        raise CanaryError("trust verdict record has no verified exact subject store")

    admission = record.get("producer_admission")
    if not isinstance(admission, dict):
        raise CanaryError("trust verdict producer admission is missing")
    expected_admission = {
        "schema": "abyss_machine_artifact_producer_admission_v1",
        "status": "candidate_admitted",
        "owner_repo": "aoa-sdk",
        "source_ref": sdk_source_ref,
        "canonical_owner_repo": "aoa-routing",
        "canonical_predecessor_source_ref": predecessor_source_ref,
        "runtime_consumer": "abyss-stack",
        "stronger_owner": "abyss-machine",
        "provenance_state": "sdk_g5_candidate",
        "publication_posture": "non_publishing_canary",
        "single_canonical_owner": True,
        "canonical_switch_authorized": False,
    }
    for key, expected in expected_admission.items():
        if admission.get(key) != expected:
            raise CanaryError(f"trust verdict producer admission field drifted: {key}")
    if "runtime_canary" not in admission.get("allowed_consumer_intents", []):
        raise CanaryError("producer admission does not allow runtime_canary")
    if set(admission.get("required_controls", [])) != EXPECTED_CONTROLS:
        raise CanaryError("producer admission required controls drifted")
    authority = require_false_authority_flags(
        admission.get("g5_authority"),
        "trust verdict producer admission g5_authority",
    )

    inspected = verdict.get("inspected_claims")
    if not isinstance(inspected, dict):
        raise CanaryError("trust verdict inspected claims are missing")
    subject_identity = inspected.get("subject_identity")
    registry_latest = inspected.get("registry_latest")
    source = inspected.get("source")
    trust_root = inspected.get("trust_root")
    inspected_store = inspected.get("artifact_subject_store")
    if (
        not isinstance(subject_identity, dict)
        or subject_identity.get("subject_digest_expected") != subject_digest
        or subject_identity.get("subject_digest_matched") is not True
    ):
        raise CanaryError("trust verdict inspected subject identity is invalid")
    if (
        not isinstance(registry_latest, dict)
        or registry_latest.get("required") is not True
        or registry_latest.get("selected_record_is_latest") is not True
    ):
        raise CanaryError("trust verdict inspected latest-record claim is invalid")
    if (
        not isinstance(source, dict)
        or source.get("source_repo_matched") is not True
        or source.get("source_ref_matched") is not True
        or source.get("source_ref_actual") != sdk_source_ref
    ):
        raise CanaryError("trust verdict inspected source claim is invalid")
    if (
        not isinstance(trust_root, dict)
        or trust_root.get("trust_root_mode_actual") != "host_managed"
        or trust_root.get("trust_root_mode_matched") is not True
    ):
        raise CanaryError("trust verdict inspected trust-root claim is invalid")
    if (
        not isinstance(inspected_store, dict)
        or inspected_store.get("ok") is not True
        or inspected_store.get("aggregate_digest") != subject_digest
    ):
        raise CanaryError("trust verdict inspected subject-store claim is invalid")
    return authority


def absolute_existing_directory(value: str, label: str) -> Path:
    raw = Path(value)
    if not raw.is_absolute():
        raise CanaryError(f"{label} must be an absolute path")
    if raw.is_symlink():
        raise CanaryError(f"{label} must not be a symlink")
    try:
        resolved = raw.resolve(strict=True)
    except FileNotFoundError as exc:
        raise CanaryError(f"{label} is missing: {raw}") from exc
    if not resolved.is_dir():
        raise CanaryError(f"{label} must be a directory: {resolved}")
    return resolved


def absolute_existing_file(value: str, label: str) -> Path:
    raw = Path(value)
    if not raw.is_absolute():
        raise CanaryError(f"{label} must be an absolute path")
    if raw.is_symlink():
        raise CanaryError(f"{label} must not be a symlink")
    try:
        resolved = raw.resolve(strict=True)
    except FileNotFoundError as exc:
        raise CanaryError(f"{label} is missing: {raw}") from exc
    if not resolved.is_file():
        raise CanaryError(f"{label} must be a file: {resolved}")
    return resolved


def validate_inputs(
    args: argparse.Namespace,
) -> tuple[list[str], dict[str, bool], dict[str, dict[str, Any]]]:
    sdk_source_ref = require_git_object_id(args.sdk_source_ref, "SDK source ref")
    predecessor_source_ref = require_git_object_id(
        args.predecessor_source_ref,
        "predecessor source ref",
    )
    subject_digest = require_sha256_digest(args.subject_digest, "subject digest")
    routing_config = absolute_existing_file(args.routing_config, "routing config")
    subject_store = absolute_existing_directory(args.subject_store, "subject store")
    trust_path = absolute_existing_file(args.trust_verdict, "trust verdict")
    required_files = routing_required_files(routing_config)
    subject_entries = validate_subject_store(
        subject_store,
        required_files=required_files,
        subject_digest=subject_digest,
    )
    trust_verdict = read_json(trust_path, "trust verdict")
    authority = validate_trust_verdict(
        trust_verdict,
        sdk_source_ref=sdk_source_ref,
        predecessor_source_ref=predecessor_source_ref,
        subject_digest=subject_digest,
    )
    return required_files, authority, subject_entries


def candidate_manifest(
    *,
    target_root: Path,
    required_files: list[str],
    trust_verdict: dict[str, Any],
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
        "routing_producer_posture": CANARY_POSTURE,
        "canary_activation_mode": activation_mode,
        "operator_change_ref": operator_change_ref,
        "source_git_commit": sdk_source_ref,
        "generated_at_utc": observed_at,
        "refresh_command": "scripts/aoa-routing-canary materialize --explicit-exact-inputs",
        "required_file_count": len(required_files),
        "required_files": required_files,
        "file_sha256": {
            relative: file_digest_hex(target_root / relative)
            for relative in required_files
        },
        "artifact_subject_digest": subject_digest,
        "mirror_is_authority": False,
        "canonical_producer": {
            "owner_repo": "aoa-routing",
            "source_ref": predecessor_source_ref,
        },
        "candidate_producer": {
            "owner_repo": "aoa-sdk",
            "source_ref": sdk_source_ref,
            "canonical_switch_authorized": False,
        },
        "g5_authority": authority,
        "trust_verdict": trust_verdict,
    }


def validate_candidate_root(
    target_root: Path,
    *,
    required_files: list[str],
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
    subject_entries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    manifest_path = target_root / "manifest" / "federation_mirror_manifest.json"
    manifest = read_json(manifest_path, "routing canary manifest")
    expected_fields = {
        "schema": "abyss_stack_federation_mirror_manifest_v1",
        "layer": "aoa-routing",
        "routing_producer_posture": CANARY_POSTURE,
        "source_git_commit": sdk_source_ref,
        "required_file_count": len(required_files),
        "required_files": required_files,
        "artifact_subject_digest": subject_digest,
        "mirror_is_authority": False,
    }
    for key, expected in expected_fields.items():
        if manifest.get(key) != expected:
            raise CanaryError(f"routing canary manifest field drifted: {key}")
    activation_mode = manifest.get("canary_activation_mode")
    if activation_mode not in {"isolated", "authorized_live_canary"}:
        raise CanaryError("routing canary activation mode is invalid")
    operator_change_ref = manifest.get("operator_change_ref")
    if activation_mode == "authorized_live_canary":
        if not isinstance(operator_change_ref, str) or not operator_change_ref:
            raise CanaryError("live routing canary operator change ref is missing")
    elif operator_change_ref is not None:
        raise CanaryError("isolated routing canary must not claim an operator change ref")
    canonical = manifest.get("canonical_producer")
    candidate = manifest.get("candidate_producer")
    if canonical != {
        "owner_repo": "aoa-routing",
        "source_ref": predecessor_source_ref,
    }:
        raise CanaryError("routing canary canonical predecessor binding drifted")
    if candidate != {
        "owner_repo": "aoa-sdk",
        "source_ref": sdk_source_ref,
        "canonical_switch_authorized": False,
    }:
        raise CanaryError("routing canary candidate producer binding drifted")
    authority = require_false_authority_flags(
        manifest.get("g5_authority"),
        "routing canary manifest g5_authority",
    )
    validate_trust_verdict(
        manifest.get("trust_verdict")
        if isinstance(manifest.get("trust_verdict"), dict)
        else {},
        sdk_source_ref=sdk_source_ref,
        predecessor_source_ref=predecessor_source_ref,
        subject_digest=subject_digest,
    )

    hashes = manifest.get("file_sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(required_files):
        raise CanaryError("routing canary manifest hash set drifted")
    for relative in required_files:
        path = resolved_subject_file(target_root, relative)
        actual = file_digest_hex(path)
        expected = subject_entries[relative].get("sha256_hex")
        if hashes.get(relative) != actual:
            raise CanaryError(f"routing canary materialized file digest drifted: {relative}")
        if actual != expected:
            raise CanaryError(
                f"routing canary file no longer matches the subject-store ledger: {relative}"
            )

    router = read_json(target_root / "generated" / "aoa_router.min.json", "routing router")
    identity = router.get("artifact_identity")
    if (
        not isinstance(identity, dict)
        or identity.get("owner_repo") != "aoa-sdk"
        or identity.get("artifact_class") != ARTIFACT_CLASS
        or identity.get("abi_epoch") != ABI_EPOCH
    ):
        raise CanaryError("routing canary router identity is not the SDK stable ABI")
    return {
        "ok": True,
        "schema": "abyss_stack_routing_canary_check_v1",
        "posture": CANARY_POSTURE,
        "target_root": str(target_root),
        "sdk_source_ref": sdk_source_ref,
        "canonical_predecessor_source_ref": predecessor_source_ref,
        "artifact_subject_digest": subject_digest,
        "required_file_count": len(required_files),
        "g5_authority": authority,
        "canonical_switch_authorized": False,
        "closure_authorized": False,
        "activation_mode": activation_mode,
        "operator_change_ref_present": isinstance(operator_change_ref, str),
    }


def is_live_target_shape(target: Path) -> bool:
    return (
        target.name == "aoa-routing"
        and target.parent.name == "federation"
        and target.parent.parent.name == "Knowledge"
    )


def ensure_live_target_shape(target: Path) -> None:
    if not is_live_target_shape(target):
        raise CanaryError(
            "authorized live target must end in Knowledge/federation/aoa-routing"
        )


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    required_files, authority, subject_entries = validate_inputs(args)
    target = absolute_runtime_path(args.target_root, "target root")
    subject_root = absolute_existing_directory(args.subject_store, "subject store")
    live = bool(args.authorized_live_canary)
    if live:
        ensure_live_target_shape(target)
        if not args.operator_change_ref:
            raise CanaryError(
                "authorized live canary requires --operator-change-ref"
            )
        args.operator_change_ref = require_operator_change_ref(
            args.operator_change_ref
        )
    else:
        if is_live_target_shape(target):
            raise CanaryError(
                "a live-shaped routing target requires "
                "--authorized-live-canary"
            )
        if args.operator_change_ref is not None:
            raise CanaryError(
                "isolated canary must not accept --operator-change-ref"
            )
    rollback = (
        absolute_runtime_path(args.rollback_root, "rollback root")
        if args.rollback_root
        else None
    )
    if target.exists() and rollback is None:
        raise CanaryError("replacing an existing target requires --rollback-root")
    if live and (not target.is_dir() or rollback is None):
        raise CanaryError(
            "authorized live canary requires an existing target and --rollback-root"
        )
    if rollback is not None:
        if rollback.exists():
            raise CanaryError(f"rollback root already exists: {rollback}")
        if rollback == target or rollback in target.parents or target in rollback.parents:
            raise CanaryError("target and rollback roots must be disjoint")
        if rollback.parent != target.parent:
            raise CanaryError("rollback root must share the target parent for atomic activation")
    target.parent.mkdir(parents=True, exist_ok=True)

    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.sdk-canary-stage-",
            dir=target.parent,
        )
    )
    activated = False
    rolled_aside = False
    try:
        for relative in required_files:
            source = resolved_subject_file(subject_root, relative)
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if file_digest_hex(destination) != subject_entries[relative].get(
                "sha256_hex"
            ):
                raise CanaryError(
                    "copied canary file does not match the subject-store ledger: "
                    + relative
                )
        observed_at = args.observed_at or datetime.now(timezone.utc).isoformat()
        trust_verdict = read_json(Path(args.trust_verdict), "trust verdict")
        manifest = candidate_manifest(
            target_root=stage,
            required_files=required_files,
            trust_verdict=trust_verdict,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            authority=authority,
            observed_at=observed_at,
            activation_mode="authorized_live_canary" if live else "isolated",
            operator_change_ref=args.operator_change_ref if live else None,
        )
        write_json(stage / "manifest" / "federation_mirror_manifest.json", manifest)
        validate_candidate_root(
            stage,
            required_files=required_files,
            sdk_source_ref=args.sdk_source_ref,
            predecessor_source_ref=args.predecessor_source_ref,
            subject_digest=args.subject_digest,
            subject_entries=subject_entries,
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
                rolled_aside = False
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    result = validate_candidate_root(
        target,
        required_files=required_files,
        sdk_source_ref=args.sdk_source_ref,
        predecessor_source_ref=args.predecessor_source_ref,
        subject_digest=args.subject_digest,
        subject_entries=subject_entries,
    )
    result.update(
        {
            "operation": "materialize",
            "activation_mode": "authorized_live_canary" if live else "isolated",
            "activated": activated,
            "rollback_root": str(rollback) if rollback is not None else None,
        }
    )
    return result


def check(args: argparse.Namespace) -> dict[str, Any]:
    required_files, _authority, subject_entries = validate_inputs(args)
    target = absolute_runtime_path(args.target_root, "target root")
    result = validate_candidate_root(
        target,
        required_files=required_files,
        sdk_source_ref=args.sdk_source_ref,
        predecessor_source_ref=args.predecessor_source_ref,
        subject_digest=args.subject_digest,
        subject_entries=subject_entries,
    )
    result["operation"] = "check"
    return result


def inspect_rollback_candidate(
    target: Path,
    *,
    sdk_source_ref: str,
    predecessor_source_ref: str,
    subject_digest: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    manifest_path = target / "manifest" / "federation_mirror_manifest.json"
    try:
        manifest = read_json(manifest_path, "active routing canary manifest")
    except CanaryError as exc:
        return {"verified": False, "reasons": [str(exc)]}
    expected = {
        "schema": "abyss_stack_federation_mirror_manifest_v1",
        "layer": "aoa-routing",
        "routing_producer_posture": CANARY_POSTURE,
        "source_git_commit": sdk_source_ref,
        "artifact_subject_digest": subject_digest,
        "mirror_is_authority": False,
    }
    for key, expected_value in expected.items():
        if manifest.get(key) != expected_value:
            reasons.append(f"active canary field drifted: {key}")
    canonical = manifest.get("canonical_producer")
    if not isinstance(canonical, dict) or canonical.get(
        "source_ref"
    ) != predecessor_source_ref:
        reasons.append("active canary predecessor ref drifted")
    try:
        require_false_authority_flags(
            manifest.get("g5_authority"),
            "active canary g5_authority",
        )
    except CanaryError as exc:
        reasons.append(str(exc))
    return {"verified": not reasons, "reasons": reasons}


def rollback(args: argparse.Namespace) -> dict[str, Any]:
    sdk_source_ref = require_git_object_id(args.sdk_source_ref, "SDK source ref")
    predecessor_source_ref = require_git_object_id(
        args.predecessor_source_ref,
        "predecessor source ref",
    )
    subject_digest = require_sha256_digest(args.subject_digest, "subject digest")
    operator_change_ref = require_operator_change_ref(args.operator_change_ref)
    target = absolute_runtime_path(args.target_root, "target root")
    ensure_live_target_shape(target)
    rollback_root = absolute_runtime_path(args.rollback_root, "rollback root")
    candidate_retain_root = absolute_runtime_path(
        args.candidate_retain_root,
        "candidate retain root",
    )
    roots = {target, rollback_root, candidate_retain_root}
    if len(roots) != 3 or any(
        left in right.parents or right in left.parents
        for left in roots
        for right in roots
        if left != right
    ):
        raise CanaryError("target, rollback, and candidate-retain roots must be disjoint")
    if not target.is_dir() or not rollback_root.is_dir():
        raise CanaryError("rollback requires the active canary and rollback roots")
    if candidate_retain_root.exists():
        raise CanaryError(f"candidate retain root already exists: {candidate_retain_root}")
    if not (
        target.parent == rollback_root.parent == candidate_retain_root.parent
    ):
        raise CanaryError("rollback roots must share one parent for atomic restore")
    candidate_inspection = inspect_rollback_candidate(
        target,
        sdk_source_ref=sdk_source_ref,
        predecessor_source_ref=predecessor_source_ref,
        subject_digest=subject_digest,
    )

    os.replace(target, candidate_retain_root)
    try:
        os.replace(rollback_root, target)
    except Exception:
        os.replace(candidate_retain_root, target)
        raise
    return {
        "ok": True,
        "schema": "abyss_stack_routing_canary_rollback_v1",
        "operation": "rollback",
        "restored": True,
        "target_root": str(target),
        "candidate_retain_root": str(candidate_retain_root),
        "artifact_subject_digest": subject_digest,
        "operator_change_ref": operator_change_ref,
        "candidate_identity_inspection": candidate_inspection,
        "canonical_switch_authorized": False,
    }


def add_exact_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--subject-store", required=True)
    parser.add_argument("--trust-verdict", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--sdk-source-ref", required=True)
    parser.add_argument("--predecessor-source-ref", required=True)
    parser.add_argument("--subject-digest", required=True)
    parser.add_argument("--routing-config", default=str(DEFAULT_ROUTING_CONFIG))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize or verify an exact non-canonical SDK routing canary."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    materialize_parser = subparsers.add_parser("materialize")
    add_exact_input_args(materialize_parser)
    mode = materialize_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--isolated", action="store_true")
    mode.add_argument("--authorized-live-canary", action="store_true")
    materialize_parser.add_argument("--rollback-root")
    materialize_parser.add_argument("--observed-at")
    materialize_parser.add_argument("--operator-change-ref")
    materialize_parser.set_defaults(handler=materialize)

    check_parser = subparsers.add_parser("check")
    add_exact_input_args(check_parser)
    check_parser.set_defaults(handler=check)

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--authorized-live-canary", action="store_true", required=True)
    rollback_parser.add_argument("--target-root", required=True)
    rollback_parser.add_argument("--rollback-root", required=True)
    rollback_parser.add_argument("--candidate-retain-root", required=True)
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
            "schema": "abyss_stack_routing_canary_error_v1",
            "operation": args.command,
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
