"""Materialize one exact last-known-good rollback candidate without a verdict."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import RuntimeObservation
from .core import _reject_secret_material, canonical_json_bytes
from .observation import (
    DEFAULT_REGISTRY_PATH,
    DEFAULT_TARGETS_PATH,
    ObservationProducerError,
    _digest,
    _load_targets,
    _read_json,
    _write_atomic,
)


DEFAULT_DEPLOYMENT_RECORD = Path(
    "/srv/AbyssOS/abyss-stack/Logs/mcp/deployments/latest.json"
)
DEFAULT_STACK_SOURCE_ROOT = Path("/srv/AbyssOS/abyss-stack-source")
DEFAULT_STACK_RUNTIME_ROOT = Path("/srv/AbyssOS/abyss-stack")
DEFAULT_SECRET_DIR = DEFAULT_STACK_RUNTIME_ROOT / "Secrets" / "Configs"
MAX_TTL_SECONDS = 300
MAX_FUTURE_SKEW = timedelta(seconds=30)


class RollbackCandidateError(ObservationProducerError):
    """The supplied evidence cannot name one restorable LKG contour."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _file_digest(path: Path, label: str) -> str:
    absolute = path.expanduser().absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise RollbackCandidateError(f"{label} must be a regular non-symlink file")
    digest = hashlib.sha256()
    try:
        with absolute.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RollbackCandidateError(f"{label} is unreadable") from exc
    return "sha256:" + digest.hexdigest()


def _tree_identity(root: Path) -> tuple[str, int, int]:
    absolute = root.expanduser().absolute()
    if absolute.is_symlink() or not absolute.is_dir():
        raise RollbackCandidateError("deployed package must be a non-symlink directory")
    records: list[dict[str, Any]] = []
    total = 0
    for directory, directory_names, file_names in os.walk(
        absolute, topdown=True, followlinks=False
    ):
        current = Path(directory)
        retained: list[str] = []
        for name in sorted(directory_names):
            candidate = current / name
            relative = candidate.relative_to(absolute)
            if any(part in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} for part in relative.parts):
                continue
            if candidate.is_symlink() or not candidate.is_dir():
                raise RollbackCandidateError("deployed package contains an unsafe directory")
            retained.append(name)
        directory_names[:] = retained
        for name in sorted(file_names):
            candidate = current / name
            relative = candidate.relative_to(absolute)
            if relative.name == ".coverage" or relative.suffix == ".pyc" or relative.name.endswith(".egg-info"):
                continue
            if candidate.is_symlink() or not candidate.is_file():
                raise RollbackCandidateError("deployed package contains an unsafe file")
            metadata = candidate.stat()
            total += metadata.st_size
            records.append(
                {
                    "path": relative.as_posix(),
                    "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                    "size": metadata.st_size,
                    "sha256": _file_digest(candidate, "deployed package file"),
                }
            )
    records.sort(key=lambda item: item["path"])
    digest = "sha256:" + hashlib.sha256(canonical_json_bytes(records)).hexdigest()
    return digest, len(records), total


def _git_package_identity(
    source_root: Path,
    revision: str,
    service_id: str,
) -> tuple[str, int, int]:
    prefix = f"mcp/services/{service_id}/"
    try:
        listing = subprocess.run(
            (
                "git",
                "-c",
                "core.useReplaceRefs=false",
                "-C",
                str(source_root.expanduser().absolute()),
                "ls-tree",
                "-rz",
                "--full-tree",
                revision,
                "--",
                prefix.removesuffix("/"),
            ),
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RollbackCandidateError("LKG stack source revision is unavailable") from exc
    records: list[dict[str, Any]] = []
    total = 0
    for raw in listing.split(b"\0"):
        if not raw:
            continue
        try:
            header, raw_path = raw.split(b"\t", 1)
            mode, kind, object_id = header.decode("ascii").split(" ")
            full_path = raw_path.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise RollbackCandidateError("LKG Git tree entry is invalid") from exc
        if kind != "blob" or mode not in {"100644", "100755"} or not full_path.startswith(prefix):
            raise RollbackCandidateError("LKG Git package contains an unsupported entry")
        relative = full_path.removeprefix(prefix)
        try:
            content = subprocess.run(
                (
                    "git",
                    "-c",
                    "core.useReplaceRefs=false",
                    "-C",
                    str(source_root.expanduser().absolute()),
                    "cat-file",
                    "blob",
                    object_id,
                ),
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RollbackCandidateError("LKG Git package blob is unavailable") from exc
        total += len(content)
        records.append(
            {
                "path": relative,
                "mode": "0755" if mode == "100755" else "0644",
                "size": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        )
    if not records:
        raise RollbackCandidateError("LKG Git package is empty")
    records.sort(key=lambda item: item["path"])
    digest = "sha256:" + hashlib.sha256(canonical_json_bytes(records)).hexdigest()
    return digest, len(records), total


def _credential_present(secret_dir: Path, service_id: str) -> bool:
    path = secret_dir.expanduser().absolute() / f"{service_id}-read-bearer-token"
    if path.is_symlink() or not path.is_file():
        return False
    metadata = path.stat()
    return stat.S_IMODE(metadata.st_mode) == 0o600 and 0 < metadata.st_size <= 8192


def _exact_link_expiries(link: Any, label: str) -> list[datetime]:
    if link.state != "exact" or not link.evidence_refs:
        raise RollbackCandidateError(f"{label} evidence is not exact")
    return [link.expires_at, *(item.expires_at for item in link.evidence_refs)]


def _validate_manifest(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    if (
        payload.get("schema_version") != "abyss_stack_mcp_deployment_manifest_v1"
        or payload.get("provider") != "abyss-stack"
        or payload.get("parity_state") != "exact"
        or payload.get("contains_secrets") is not False
    ):
        raise RollbackCandidateError("deployment record is not an exact stack receipt")
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"manifest_id", "record_ref", "latest_ref"}
    }
    manifest_id = _digest(body)
    expected_ref = (
        "Logs/mcp/deployments/records/"
        + manifest_id.removeprefix("sha256:")
        + ".json"
    )
    if payload.get("manifest_id") != manifest_id or payload.get("record_ref") != expected_ref:
        raise RollbackCandidateError("deployment record content address is invalid")
    if path.name != expected_ref.rsplit("/", 1)[1]:
        raise RollbackCandidateError("deployment input is not the immutable manifest record")
    return payload


def build_rollback_candidate(
    *,
    observation_path: Path,
    deployment_record_path: Path,
    registry_path: Path,
    consumer_id: str,
    targets_path: Path = DEFAULT_TARGETS_PATH,
    stack_source_root: Path = DEFAULT_STACK_SOURCE_ROOT,
    stack_runtime_root: Path = DEFAULT_STACK_RUNTIME_ROOT,
    secret_dir: Path = DEFAULT_SECRET_DIR,
    ttl_seconds: int = MAX_TTL_SECONDS,
    clock: Callable[[], datetime] = _now,
    git_identity: Callable[[Path, str, str], tuple[str, int, int]] = _git_package_identity,
    deployed_identity: Callable[[Path], tuple[str, int, int]] = _tree_identity,
) -> dict[str, Any]:
    if not 30 <= ttl_seconds <= MAX_TTL_SECONDS:
        raise RollbackCandidateError("rollback candidate TTL must be 30..300 seconds")
    observation_payload, _ = _read_json(observation_path, "runtime observation")
    manifest_payload, _ = _read_json(deployment_record_path, "deployment record")
    registry_payload, _ = _read_json(registry_path, "private organ registry")
    _reject_secret_material(observation_payload)
    _reject_secret_material(manifest_payload)
    _reject_secret_material(registry_payload)
    try:
        observation = RuntimeObservation.model_validate(observation_payload)
    except ValidationError as exc:
        raise RollbackCandidateError("runtime observation failed its stack contract") from exc
    manifest = _validate_manifest(manifest_payload, deployment_record_path)
    catalog, _ = _load_targets(targets_path)
    target = next((item for item in catalog.targets if item.organ_id == "aoa-kag"), None)
    subjects = [
        item
        for item in observation.subjects
        if item.organ_id == "aoa-kag" and item.policy_family == "read"
    ]
    if target is None or len(subjects) != 1:
        raise RollbackCandidateError("KAG read rollback target is unavailable")
    subject = subjects[0]
    now = clock().astimezone(timezone.utc)
    if observation.generated_at > now + MAX_FUTURE_SKEW or observation.expires_at <= now:
        raise RollbackCandidateError("runtime observation is not current")
    if (
        not subject.process.active
        or not subject.endpoint.ready
        or subject.registry.registry_state not in {"shadow", "admitted"}
        or subject.owners.runtime_owner != "abyss-stack"
        or subject.owners.proof_owner != "aoa-evals"
        or target.canary_contract is None
    ):
        raise RollbackCandidateError("runtime contour cannot support rollback readiness")
    expiries = [observation.expires_at]
    for label, link in (
        ("source", subject.source.evidence),
        ("package", subject.package.evidence),
        ("deploy", subject.deploy.evidence),
        ("process", subject.process.evidence),
        ("endpoint", subject.endpoint.evidence),
        ("registry", subject.registry.evidence),
        ("freshness", subject.freshness),
        ("last-known-good canary", subject.canary.evidence),
    ):
        expiries.extend(_exact_link_expiries(link, label))
    matching_consumers = [
        item
        for item in subject.consumers
        if item.consumer_id == consumer_id
        and item.registered
        and item.observed_schema_digest == subject.endpoint.server_schema_digest
        and set(item.observed_protocol_versions) & set(subject.endpoint.protocol_versions)
        and item.evidence.state == "exact"
    ]
    if len(matching_consumers) != 1:
        raise RollbackCandidateError("LKG consumer registration is not exact")
    consumer = matching_consumers[0]
    expiries.extend(_exact_link_expiries(consumer.evidence, "consumer"))
    expected_lkg_route = target.canary_route + "/last-known-good"
    if (
        not subject.canary.succeeded
        or not subject.canary.result_grounded
        or subject.canary.canary_route != expected_lkg_route
        or subject.canary.canary_ref is None
        or "/rollback-canaries/records/aoa-kag/" not in subject.canary.canary_ref
    ):
        raise RollbackCandidateError("distinct grounded LKG canary is unavailable")
    canary_owners = {item.owner for item in subject.canary.evidence.evidence_refs}
    if not {"abyss-stack", "aoa-kag"} <= canary_owners:
        raise RollbackCandidateError("LKG canary lacks stack capture or owner review")

    _validate_manifest(manifest, deployment_record_path)
    services = manifest.get("services")
    service = next(
        (
            item
            for item in services
            if isinstance(item, dict) and item.get("service_id") == target.service_id
        ),
        None,
    ) if isinstance(services, list) else None
    if service is None:
        raise RollbackCandidateError("deployment record lacks the KAG service")
    expected_manifest = subject.deploy.manifest_digest
    if (
        manifest.get("manifest_id") != expected_manifest
        or manifest.get("record_ref") != subject.deploy.manifest_ref
        or service.get("package_digest") != subject.package.artifact_digest
        or service.get("deployed_tree", {}).get("tree_digest") != subject.deploy.tree_digest
        or service.get("source_tree", {}).get("tree_digest") != subject.package.artifact_digest
        or service.get("package_source_revision") != subject.package.source_revision
        or manifest.get("source", {}).get("revision") != subject.deploy.revision
    ):
        raise RollbackCandidateError("deployment record differs from the live LKG target")
    source_identity = git_identity(
        stack_source_root, subject.package.source_revision, target.service_id
    )
    deployed_path = stack_runtime_root / str(service.get("deployed_path"))
    runtime_identity = deployed_identity(deployed_path)
    expected_identity = (
        subject.package.artifact_digest,
        service["source_tree"]["file_count"],
        service["source_tree"]["byte_count"],
    )
    if source_identity != expected_identity or runtime_identity != expected_identity:
        raise RollbackCandidateError("LKG package is not reproducible and exact")
    executable = Path(subject.process.executable_ref)
    executable_digest = _file_digest(executable, "LKG executable")
    if subject.process.unit_name != target.unit_name or executable.as_posix() != target.executable_ref:
        raise RollbackCandidateError("LKG process target differs from the committed catalog")
    if not _credential_present(secret_dir, target.service_id):
        raise RollbackCandidateError("LKG credential file is unavailable or unsafe")
    records = registry_payload.get("records")
    record = next(
        (item for item in records if isinstance(item, dict) and item.get("organ_id") == "aoa-kag"),
        None,
    ) if isinstance(records, list) else None
    if record is None or _digest(record) != subject.registry.registry_digest:
        raise RollbackCandidateError("private registry record differs from observation")
    contours = record.get("credential_contours")
    credential_class = contours.get("read") if isinstance(contours, dict) else None
    if not isinstance(credential_class, str) or not credential_class:
        raise RollbackCandidateError("LKG read credential class is unavailable")

    expires_at = min(min(expiries), now + timedelta(seconds=ttl_seconds))
    if expires_at <= now:
        raise RollbackCandidateError("rollback candidate evidence is expired")
    process_target = (
        f"systemd-user:{target.unit_name}:executable:{executable_digest}"
    )
    target_payload = {
        "consumer_registration_ref": consumer.registration_ref,
        "package_digest": subject.package.artifact_digest,
        "deploy_revision": subject.deploy.revision,
        "deploy_tree_digest": subject.deploy.tree_digest,
        "deploy_manifest_ref": subject.deploy.manifest_ref,
        "deploy_manifest_digest": subject.deploy.manifest_digest,
        "unit_name": target.unit_name,
        "credential_class": credential_class,
        "executable_ref": target.executable_ref,
        "process_identity": process_target,
        "canary_route": subject.canary.canary_route,
        "canary_ref": subject.canary.canary_ref,
    }
    body: dict[str, Any] = {
        "schema_version": "abyss_stack_mcp_rollback_candidate_v1",
        "issuer": "abyss-stack",
        "organ_id": "aoa-kag",
        "policy_family": "read",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "rollback_route": target.rollback_route,
        "observation": {
            "observation_ref": observation_path.expanduser().absolute().as_posix(),
            "observation_digest": _digest(observation_payload),
            "generated_at": observation.generated_at.isoformat().replace("+00:00", "Z"),
            "expires_at": observation.expires_at.isoformat().replace("+00:00", "Z"),
        },
        "registry": {
            "registry_id": subject.registry.registry_id,
            "registry_digest": subject.registry.registry_digest,
            "registry_state": subject.registry.registry_state,
        },
        "source_package": {
            "source_root_owner": "abyss-stack",
            "source_revision": subject.package.source_revision,
            "source_tree_digest": source_identity[0],
            "deployed_tree_digest": runtime_identity[0],
            "file_count": source_identity[1],
            "byte_count": source_identity[2],
        },
        "last_known_good": target_payload,
        "checks": {
            "immutable_manifest_verified": True,
            "source_commit_available": True,
            "source_package_reproduced": True,
            "deployed_package_exact": True,
            "unit_and_executable_exact": True,
            "credential_present_without_read": True,
            "consumer_registration_exact": True,
            "lkg_canary_distinct_and_grounded": True,
            "runtime_effect_executed": False,
        },
        "execution_authorized": False,
        "admission_authorized": False,
        "rollback_executed": False,
        "contains_secrets": False,
        "claim_limits": [
            "This stack candidate names one reproducible last-known-good read contour; it is not a proof verdict.",
            "The credential check observes only safe file metadata and never reads or records credential bytes.",
            "No package restore, registry change, consumer change, process restart, canary replay, or admission effect was executed.",
            "Only an exact aoa-evals review projected back onto the unchanged live target can make rollback readiness observable.",
        ],
    }
    body["candidate_id"] = _digest(body)
    _reject_secret_material(body)
    return body


def write_candidate(candidate: dict[str, Any], output_path: Path) -> None:
    _write_atomic(output_path, candidate)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--deployment-record", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--consumer-id", required=True)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    parser.add_argument("--stack-source-root", type=Path, default=DEFAULT_STACK_SOURCE_ROOT)
    parser.add_argument("--stack-runtime-root", type=Path, default=DEFAULT_STACK_RUNTIME_ROOT)
    parser.add_argument("--secret-dir", type=Path, default=DEFAULT_SECRET_DIR)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ttl-seconds", type=int, default=MAX_TTL_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidate = build_rollback_candidate(
            observation_path=args.observation,
            deployment_record_path=args.deployment_record,
            registry_path=args.registry,
            consumer_id=args.consumer_id,
            targets_path=args.targets,
            stack_source_root=args.stack_source_root,
            stack_runtime_root=args.stack_runtime_root,
            secret_dir=args.secret_dir,
            ttl_seconds=args.ttl_seconds,
        )
        write_candidate(candidate, args.output)
    except (RollbackCandidateError, OSError, KeyError) as exc:
        print(f"rollback candidate: {exc}", file=os.sys.stderr)
        return 1
    print(f"output={args.output.expanduser().absolute()}")
    print(f"candidate_id={candidate['candidate_id']}")
    print("rollback_verdict_issued=false")
    print("execution_authorized=false")
    print("admission_authorized=false")
    print("contains_secrets=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
