"""Produce one bounded, secret-free runtime observation from explicit evidence.

The producer composes stack-owned deployment and systemd facts with the
private aoa-sdk registry projection.  It never reads bearer material, probes
an owner endpoint, scans sibling workspaces, or infers proof, freshness,
consumer compatibility, acceptance, canary success, or rollback readiness.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator

from .contracts import (
    CanaryObservation,
    CentralProofObservation,
    ConsumerObservation,
    DeployIdentity,
    EndpointObservation,
    EvidenceRef,
    FreshnessObservation,
    Identifier,
    LinkEvidence,
    NonEmpty,
    OwnerAcceptanceObservation,
    OwnerRoles,
    PackageIdentity,
    ProcessObservation,
    RollbackObservation,
    RuntimeObservation,
    RuntimeSubject,
    SourceIdentity,
    StrictModel,
    UnitName,
)
from .core import MAX_OBSERVATION_BYTES, _reject_secret_material, canonical_json_bytes


DEFAULT_DEPLOYMENT_MANIFEST_PATH = Path(
    "/srv/AbyssOS/abyss-stack/Logs/mcp/deployments/latest.json"
)
DEFAULT_REGISTRY_PATH = Path(
    "/srv/AbyssOS/.aoa/organ-access/organ-registry.source.json"
)
DEFAULT_OUTPUT_PATH = Path(
    "/srv/AbyssOS/abyss-stack/Logs/mcp/observations/current.json"
)
DEFAULT_OVERLAY_PATH = Path(
    "/srv/AbyssOS/abyss-stack/Logs/mcp/observations/evidence-overlay.json"
)
def _packaged_targets_path(module_path: Path) -> Path:
    """Bind the packaged catalog to the physical installed package directory.

    Python virtual environments commonly expose ``site-packages`` through a
    ``lib64 -> lib`` compatibility symlink.  Resolve only the trusted module
    location used to derive the built-in default; explicit operator-supplied
    paths still pass through the fail-closed component checks unchanged.
    """

    return module_path.resolve(strict=True).with_name("runtime-targets.v1.json")


DEFAULT_TARGETS_PATH = _packaged_targets_path(Path(__file__))
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_OVERLAY_FUTURE_SKEW = timedelta(seconds=30)
UNKNOWN_DIGEST = "sha256:" + ("0" * 64)
ObservationCanaryPurpose = Literal["current", "last-known-good"]


class ObservationProducerError(ValueError):
    """Fail-closed production error without secret-bearing detail."""


class CanaryArrayContains(StrictModel):
    pointer: NonEmpty
    subset: dict[str, Any]

    @field_validator("pointer")
    @classmethod
    def require_json_pointer(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("canary pointer must be an absolute JSON pointer")
        return value


class RuntimeCanaryContract(StrictModel):
    tool_name: Identifier
    arguments: dict[str, Any]
    schema_pointer: NonEmpty
    schema_value: NonEmpty
    required_pointers: tuple[NonEmpty, ...] = ()
    exact_values: dict[NonEmpty, Any] = Field(default_factory=dict)
    array_contains: tuple[CanaryArrayContains, ...] = ()

    @field_validator("schema_pointer")
    @classmethod
    def require_schema_pointer(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("canary schema pointer must be an absolute JSON pointer")
        return value

    @field_validator("required_pointers")
    @classmethod
    def require_absolute_pointers(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not pointer.startswith("/") for pointer in value):
            raise ValueError("canary required pointers must be absolute JSON pointers")
        if len(value) != len(set(value)):
            raise ValueError("canary required pointers must be unique")
        return value

    @field_validator("exact_values")
    @classmethod
    def require_absolute_exact_pointers(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if any(not pointer.startswith("/") for pointer in value):
            raise ValueError(
                "canary exact-value pointers must be absolute JSON pointers"
            )
        return value


class RuntimeTarget(StrictModel):
    organ_id: Identifier
    registry_organ_id: Identifier
    service_id: Identifier
    policy_family: Literal["read"] = "read"
    unit_name: UnitName
    executable_ref: NonEmpty
    endpoint_ref: NonEmpty
    protocol_versions: tuple[NonEmpty, ...] = Field(min_length=1)
    effect_classes: tuple[Literal["observe", "derive", "validate"], ...] = Field(
        min_length=1
    )
    consumer_evidence_owners: tuple[Identifier, ...] = ("8Dionysus",)
    canary_route: NonEmpty
    canary_contract: RuntimeCanaryContract | None = None
    rollback_route: NonEmpty


class RuntimeTargetCatalog(StrictModel):
    schema_version: Literal["abyss_stack_runtime_targets_v1"] = (
        "abyss_stack_runtime_targets_v1"
    )
    targets: tuple[RuntimeTarget, ...] = Field(min_length=1)

    @field_validator("targets")
    @classmethod
    def require_unique_targets(
        cls,
        value: tuple[RuntimeTarget, ...],
    ) -> tuple[RuntimeTarget, ...]:
        organ_keys = [(target.organ_id, target.policy_family) for target in value]
        registry_ids = [target.registry_organ_id for target in value]
        service_ids = [target.service_id for target in value]
        unit_names = [target.unit_name for target in value]
        endpoint_refs = [target.endpoint_ref for target in value]
        for label, identities in (
            ("organ/policy targets", organ_keys),
            ("registry organ ids", registry_ids),
            ("service ids", service_ids),
            ("unit names", unit_names),
            ("endpoint refs", endpoint_refs),
        ):
            if len(identities) != len(set(identities)):
                raise ValueError(f"{label} must be unique")
        return value


class RuntimeEvidenceOverlaySubject(StrictModel):
    organ_id: Identifier
    policy_family: Literal["read"] = "read"
    source: SourceIdentity | None = None
    endpoint: EndpointObservation | None = None
    consumers: tuple[ConsumerObservation, ...] | None = None
    freshness: FreshnessObservation | None = None
    proof: CentralProofObservation | None = None
    acceptance: OwnerAcceptanceObservation | None = None
    canary: CanaryObservation | None = None
    rollback: RollbackObservation | None = None


class RuntimeEvidenceOverlay(StrictModel):
    schema_version: Literal["abyss_stack_runtime_evidence_overlay_v1"] = (
        "abyss_stack_runtime_evidence_overlay_v1"
    )
    generated_at: datetime
    expires_at: datetime
    contains_secrets: Literal[False] = False
    subjects: tuple[RuntimeEvidenceOverlaySubject, ...]

    @field_validator("generated_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("overlay timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("subjects")
    @classmethod
    def require_unique_subjects(
        cls,
        value: tuple[RuntimeEvidenceOverlaySubject, ...],
    ) -> tuple[RuntimeEvidenceOverlaySubject, ...]:
        keys = [(subject.organ_id, subject.policy_family) for subject in value]
        if len(keys) != len(set(keys)):
            raise ValueError("overlay organ/policy targets must be unique")
        return value


SystemctlRunner = Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ObservationProducerError(f"{label} must be an RFC 3339 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ObservationProducerError(
            f"{label} must be an RFC 3339 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ObservationProducerError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    path = _require_no_symlink_components(path, label)
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ObservationProducerError(
                    f"{label} must be a regular non-symlink file"
                )
            if metadata.st_size > MAX_INPUT_BYTES:
                raise ObservationProducerError(f"{label} exceeds the 2 MiB input limit")
            chunks: list[bytes] = []
            remaining = MAX_INPUT_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ObservationProducerError(
                f"{label} must be a regular non-symlink file"
            ) from exc
        raise ObservationProducerError(f"{label} is unavailable") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise ObservationProducerError(f"{label} exceeds the 2 MiB input limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ObservationProducerError(f"{label} contains malformed JSON") from exc
    if not isinstance(value, dict):
        raise ObservationProducerError(f"{label} must contain one JSON object")
    return value, raw


def _require_no_symlink_components(path: Path, label: str) -> Path:
    absolute = path.expanduser().absolute()
    for component in tuple(reversed(absolute.parents)) + (absolute,):
        if component.exists() or component.is_symlink():
            if component.is_symlink():
                raise ObservationProducerError(f"{label} cannot traverse a symlink")
    return absolute


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = _require_no_symlink_components(path, "observation output")
    parent = _require_no_symlink_components(path.parent, "observation output root")
    if not parent.is_dir():
        raise ObservationProducerError(
            "observation output root must be a non-symlink directory"
        )
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ObservationProducerError(
            "observation output must be a regular non-symlink file"
        )
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    if len(content) > MAX_OBSERVATION_BYTES:
        raise ObservationProducerError("produced observation exceeds the 2 MiB limit")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _load_targets(path: Path) -> tuple[RuntimeTargetCatalog, str]:
    payload, _ = _read_json(path, "runtime target catalog")
    _reject_secret_material(payload)
    try:
        catalog = RuntimeTargetCatalog.model_validate(payload)
    except ValidationError as exc:
        raise ObservationProducerError(
            "runtime target catalog failed contract validation"
        ) from exc
    return catalog, _digest(catalog.model_dump(mode="json"))


def _load_deployment(path: Path) -> tuple[dict[str, Any], str]:
    payload, raw = _read_json(path, "deployment manifest")
    if (
        payload.get("schema_version") != "abyss_stack_mcp_deployment_manifest_v1"
        or payload.get("digest_scope") != "abyss_stack_mcp_deployment_body_v1"
        or payload.get("provider") != "abyss-stack"
        or payload.get("contains_secrets") is not False
        or payload.get("parity_state") != "exact"
    ):
        raise ObservationProducerError(
            "deployment manifest is not an exact secret-free stack receipt"
        )
    unsigned = {
        key: value
        for key, value in payload.items()
        if key not in {"manifest_id", "record_ref", "latest_ref"}
    }
    expected = _digest(unsigned)
    expected_ref = (
        "Logs/mcp/deployments/records/" + expected.removeprefix("sha256:") + ".json"
    )
    if (
        payload.get("manifest_id") != expected
        or payload.get("record_ref") != expected_ref
        or payload.get("latest_ref") != "Logs/mcp/deployments/latest.json"
    ):
        raise ObservationProducerError("deployment manifest content address is invalid")
    if path.name == "latest.json":
        record = path.parent / "records" / Path(expected_ref).name
        _, record_raw = _read_json(record, "immutable deployment record")
        if record_raw != raw:
            raise ObservationProducerError(
                "latest deployment manifest differs from its immutable record"
            )
    services = payload.get("services")
    if not isinstance(services, list):
        raise ObservationProducerError("deployment manifest services are invalid")
    service_ids = [
        service.get("service_id") for service in services if isinstance(service, dict)
    ]
    if len(service_ids) != len(services) or len(service_ids) != len(set(service_ids)):
        raise ObservationProducerError(
            "deployment manifest service identities are invalid"
        )
    return payload, expected


def _load_registry(path: Path) -> tuple[dict[str, Any], str]:
    payload, _ = _read_json(path, "private organ registry")
    schema_version = payload.get("schema_version")
    if (
        schema_version
        not in {"aoa_organ_registry_source_v1", "aoa_organ_registry_source_v2"}
        or payload.get("contains_secrets") is not False
        or payload.get("default_admission") != "deny"
    ):
        raise ObservationProducerError(
            "private organ registry is not a deny-by-default secret-free source"
        )
    records = payload.get("records")
    if not isinstance(records, list):
        raise ObservationProducerError("private organ registry records are invalid")
    organ_ids = [
        record.get("organ_id") for record in records if isinstance(record, dict)
    ]
    if len(organ_ids) != len(records) or len(organ_ids) != len(set(organ_ids)):
        raise ObservationProducerError("private organ registry identities are invalid")
    if schema_version == "aoa_organ_registry_source_v2":
        contour_keys: list[tuple[str, str]] = []
        for record in records:
            contours = record.get("contours") if isinstance(record, dict) else None
            if not isinstance(contours, list) or not contours:
                raise ObservationProducerError(
                    "private v2 organ registry contours are invalid"
                )
            for contour in contours:
                contour_id = (
                    contour.get("contour_id") if isinstance(contour, dict) else None
                )
                policy_family = (
                    contour.get("policy_family")
                    if isinstance(contour, dict)
                    else None
                )
                if (
                    not isinstance(contour_id, str)
                    or not contour_id
                    or contour_id != policy_family
                ):
                    raise ObservationProducerError(
                        "private v2 organ registry contour identity is invalid"
                    )
                contour_keys.append((record["organ_id"], contour_id))
        if len(contour_keys) != len(set(contour_keys)):
            raise ObservationProducerError(
                "private v2 organ registry contour identities are ambiguous"
            )
    return payload, _digest(payload)


def _systemctl(
    arguments: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _link(
    *,
    state: str,
    observed_at: datetime,
    expires_at: datetime,
    refs: tuple[EvidenceRef, ...] = (),
    reasons: tuple[str, ...] = (),
) -> LinkEvidence:
    return LinkEvidence(
        state=state,
        observed_at=observed_at,
        expires_at=expires_at,
        evidence_refs=refs,
        reason_codes=reasons,
    )


def _manifest_ref(
    manifest: dict[str, Any],
    *,
    observed_at: datetime,
    expires_at: datetime,
) -> EvidenceRef:
    source = manifest.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("revision"), str):
        raise ObservationProducerError("deployment manifest source is invalid")
    return EvidenceRef(
        owner="abyss-stack",
        evidence_ref=manifest["record_ref"],
        revision=source["revision"],
        observed_at=observed_at,
        expires_at=expires_at,
    )


def _source_evidence(
    record: dict[str, Any],
    *,
    observed_at: datetime,
    expires_at: datetime,
) -> tuple[EvidenceRef, ...]:
    maturity = record.get("maturity")
    declared = maturity.get("declared") if isinstance(maturity, dict) else None
    evidence = declared.get("evidence") if isinstance(declared, dict) else None
    if not isinstance(evidence, dict):
        return ()
    try:
        parsed = EvidenceRef.model_validate(evidence)
    except ValidationError:
        return ()
    if parsed.observed_at > observed_at + MAX_OVERLAY_FUTURE_SKEW:
        return ()
    if parsed.expires_at is not None and parsed.expires_at <= observed_at:
        return (parsed,)
    return (parsed,)


def _process_observation(
    target: RuntimeTarget,
    *,
    observed_at: datetime,
    expires_at: datetime,
    deployment_revision: str,
    runner: SystemctlRunner,
) -> ProcessObservation:
    command = (
        "systemctl",
        "--user",
        "show",
        target.unit_name,
        "--property=LoadState",
        "--property=ActiveState",
        "--property=MainPID",
        "--property=ExecMainStartTimestampMonotonic",
        "--property=FragmentPath",
        "--no-pager",
    )
    try:
        completed = runner(command)
    except (OSError, subprocess.SubprocessError):
        completed = subprocess.CompletedProcess(command, 1, "", "")
    if completed.returncode != 0:
        return ProcessObservation(
            unit_name=target.unit_name,
            executable_ref=target.executable_ref,
            active=False,
            process_identity=None,
            evidence=_link(
                state="unknown",
                observed_at=observed_at,
                expires_at=expires_at,
                reasons=("systemd-unit-unobserved",),
            ),
        )
    properties: dict[str, str] = {}
    for raw_line in completed.stdout.splitlines():
        key, separator, value = raw_line.partition("=")
        if separator and key:
            properties[key] = value
    if properties.get("LoadState") != "loaded" or not properties.get("FragmentPath"):
        return ProcessObservation(
            unit_name=target.unit_name,
            executable_ref=target.executable_ref,
            active=False,
            process_identity=None,
            evidence=_link(
                state="unknown",
                observed_at=observed_at,
                expires_at=expires_at,
                reasons=("systemd-unit-unavailable",),
            ),
        )
    active = properties.get("ActiveState") == "active"
    try:
        pid = int(properties.get("MainPID", "0"))
        start = int(properties.get("ExecMainStartTimestampMonotonic", "0"))
    except ValueError:
        pid = 0
        start = 0
    if active and (pid <= 0 or start <= 0):
        return ProcessObservation(
            unit_name=target.unit_name,
            executable_ref=target.executable_ref,
            active=False,
            process_identity=None,
            evidence=_link(
                state="blocked",
                observed_at=observed_at,
                expires_at=expires_at,
                reasons=("active-process-identity-invalid",),
            ),
        )
    process_identity = (
        f"systemd-user:{target.unit_name}:pid:{pid}:start:{start}" if active else None
    )
    status = (
        f"systemd-user:{target.unit_name}:pid:{pid}:start:{start}"
        if active
        else f"systemd-user:{target.unit_name}:inactive"
    )
    ref = EvidenceRef(
        owner="abyss-stack",
        evidence_ref=status,
        revision=deployment_revision,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    return ProcessObservation(
        unit_name=target.unit_name,
        executable_ref=target.executable_ref,
        active=active,
        process_identity=process_identity,
        evidence=_link(
            state="exact",
            observed_at=observed_at,
            expires_at=expires_at,
            refs=(ref,),
        ),
    )


def _registry_roles(record: dict[str, Any]) -> OwnerRoles:
    owners = record.get("owners")
    if not isinstance(owners, dict):
        raise ObservationProducerError("registry owner roles are invalid")
    try:
        return OwnerRoles(
            source_owner=owners["source_owner"],
            access_owner=owners["access_owner"],
            runtime_owner=owners["runtime_owner"],
            proof_owner=owners["proof_owner"],
            acceptance_owner=owners["acceptance_owner"],
        )
    except (KeyError, ValidationError) as exc:
        raise ObservationProducerError("registry owner roles are invalid") from exc


def _registry_contour(
    record: dict[str, Any],
    *,
    schema_version: str,
    policy_family: str,
) -> dict[str, Any] | None:
    if schema_version == "aoa_organ_registry_source_v1":
        return None
    contours = record.get("contours")
    matches = [
        contour
        for contour in contours
        if isinstance(contour, dict)
        and contour.get("contour_id") == policy_family
        and contour.get("policy_family") == policy_family
    ] if isinstance(contours, list) else []
    if len(matches) != 1:
        raise ObservationProducerError(
            "target registry contour is absent or ambiguous"
        )
    return matches[0]


def _registry_declares_target(
    registry: dict[str, Any],
    target: RuntimeTarget,
) -> bool:
    if registry.get("schema_version") == "aoa_organ_registry_source_v1":
        return True
    records = [
        record
        for record in registry["records"]
        if record.get("organ_id") == target.registry_organ_id
    ]
    if len(records) > 1:
        raise ObservationProducerError("target registry organ is ambiguous")
    if not records:
        return False
    contours = records[0].get("contours")
    if not isinstance(contours, list):
        raise ObservationProducerError("target registry contours are invalid")
    return any(
        isinstance(contour, dict)
        and contour.get("contour_id") == target.policy_family
        and contour.get("policy_family") == target.policy_family
        for contour in contours
    )


def _credential_class(
    record: dict[str, Any],
    contour: dict[str, Any] | None,
) -> str:
    if contour is not None:
        value = contour.get("credential_class")
        if isinstance(value, str) and value:
            return value
        raise ObservationProducerError(
            "registry contour credential class is unavailable"
        )
    contours = record.get("credential_contours")
    value = contours.get("read") if isinstance(contours, dict) else None
    if not isinstance(value, str) or not value:
        raise ObservationProducerError("registry read credential class is unavailable")
    return value


def _build_subject(
    target: RuntimeTarget,
    *,
    manifest: dict[str, Any],
    registry: dict[str, Any],
    registry_digest: str,
    observed_at: datetime,
    expires_at: datetime,
    runner: SystemctlRunner,
    canary_purpose: ObservationCanaryPurpose,
) -> RuntimeSubject:
    services = {service["service_id"]: service for service in manifest["services"]}
    service = services.get(target.service_id)
    if not isinstance(service, dict):
        raise ObservationProducerError(
            f"target service {target.service_id} is absent from deployment manifest"
        )
    records = {record["organ_id"]: record for record in registry["records"]}
    record = records.get(target.registry_organ_id)
    if not isinstance(record, dict):
        raise ObservationProducerError(
            f"target organ {target.registry_organ_id} is absent from private registry"
        )
    schema_version = registry["schema_version"]
    contour = _registry_contour(
        record,
        schema_version=schema_version,
        policy_family=target.policy_family,
    )
    registry_subject = contour if contour is not None else record
    owners = _registry_roles(record)
    if owners.runtime_owner != "abyss-stack":
        raise ObservationProducerError("target runtime owner is not abyss-stack")
    credential_class = _credential_class(record, contour)

    source_revision: str = "unobserved"
    revisions = registry_subject.get("revisions")
    source_revision_block = (
        revisions.get("source") if isinstance(revisions, dict) else None
    )
    if isinstance(source_revision_block, dict) and isinstance(
        source_revision_block.get("revision"),
        str,
    ):
        source_revision = source_revision_block["revision"]
    source_refs = _source_evidence(
        registry_subject,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    source = SourceIdentity(
        revision=source_revision,
        tree_digest=UNKNOWN_DIGEST,
        expected_sync_tree_digest=UNKNOWN_DIGEST,
        evidence=_link(
            state="unknown",
            observed_at=observed_at,
            expires_at=expires_at,
            refs=source_refs,
            reasons=("owner-source-tree-digest-unobserved",),
        ),
    )

    manifest_ref = _manifest_ref(
        manifest,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    source_tree = service.get("source_tree")
    deployed_tree = service.get("deployed_tree")
    required_package_fields = (
        service.get("package_name"),
        service.get("package_version"),
        service.get("package_source_revision"),
        service.get("package_digest"),
        source_tree.get("tree_digest") if isinstance(source_tree, dict) else None,
        deployed_tree.get("tree_digest") if isinstance(deployed_tree, dict) else None,
    )
    if not all(isinstance(value, str) and value for value in required_package_fields):
        raise ObservationProducerError(
            f"target service {target.service_id} has incomplete package identity"
        )
    if (
        service.get("parity_state") != "exact"
        or service["package_digest"] != source_tree["tree_digest"]
        or service["package_digest"] != deployed_tree["tree_digest"]
    ):
        raise ObservationProducerError(
            f"target service {target.service_id} lacks exact package/deploy parity"
        )
    package = PackageIdentity(
        name=service["package_name"],
        version=service["package_version"],
        source_revision=service["package_source_revision"],
        artifact_digest=service["package_digest"],
        expected_deploy_tree_digest=deployed_tree["tree_digest"],
        evidence=_link(
            state="exact",
            observed_at=observed_at,
            expires_at=expires_at,
            refs=(manifest_ref,),
        ),
    )
    deployed_at = _parse_timestamp(manifest.get("deployed_at"), "deployed_at")
    deploy = DeployIdentity(
        revision=service["package_source_revision"],
        tree_digest=deployed_tree["tree_digest"],
        manifest_ref=manifest["record_ref"],
        manifest_digest=manifest["manifest_id"],
        deployed_at=deployed_at,
        evidence=_link(
            state="exact",
            observed_at=observed_at,
            expires_at=expires_at,
            refs=(manifest_ref,),
        ),
    )
    process = _process_observation(
        target,
        observed_at=observed_at,
        expires_at=expires_at,
        deployment_revision=service["package_source_revision"],
        runner=runner,
    )
    endpoint_reason = (
        "server-schema-unobserved"
        if process.active
        else "owner-bounded-process-inactive"
    )
    endpoint = EndpointObservation(
        transport="streamable-http",
        endpoint_ref=target.endpoint_ref,
        protocol_versions=target.protocol_versions,
        ready=False,
        server_schema_digest=None,
        evidence=_link(
            state="unknown",
            observed_at=observed_at,
            expires_at=expires_at,
            reasons=(endpoint_reason,),
        ),
    )

    registry_expiry = _parse_timestamp(
        registry.get("expires_at"),
        "registry expires_at",
    )
    record_digest = _digest(registry_subject)
    registry_subject_ref = target.registry_organ_id
    if contour is not None:
        registry_subject_ref += f":{target.policy_family}"
    registry_ref = EvidenceRef(
        owner="aoa-sdk",
        evidence_ref=(
            f"aoa-sdk-registry:{registry['registry_id']}:"
            f"{registry_subject_ref}:{record_digest}"
        ),
        revision=registry_digest,
        observed_at=_parse_timestamp(
            registry.get("authored_at"),
            "registry authored_at",
        ),
        expires_at=registry_expiry,
    )
    registry_state = registry_subject.get("registry_state")
    allowed_registry_states = {
        "declared",
        "package_candidate",
        "deploy_candidate",
        "shadow",
        "admitted",
        "suspended",
        "deprecated",
        "retired",
    }
    if registry_state not in allowed_registry_states:
        raise ObservationProducerError("registry state is invalid")
    registry_link_state = "exact" if registry_expiry > observed_at else "stale_readable"
    registry_reasons = (
        () if registry_link_state == "exact" else ("registry-source-expired",)
    )
    registry_link_expiry = (
        min(expires_at, registry_expiry)
        if registry_link_state == "exact"
        else expires_at
    )

    return RuntimeSubject(
        organ_id=target.organ_id,
        policy_family=target.policy_family,
        owners=owners,
        credential_class=credential_class,
        effect_classes=target.effect_classes,
        source=source,
        package=package,
        deploy=deploy,
        process=process,
        endpoint=endpoint,
        registry={
            "registry_id": registry["registry_id"],
            "registry_digest": record_digest,
            "registry_state": registry_state,
            "evidence": _link(
                state=registry_link_state,
                observed_at=observed_at,
                expires_at=registry_link_expiry,
                refs=(registry_ref,),
                reasons=registry_reasons,
            ),
        },
        consumers=(),
        freshness=FreshnessObservation(
            state="unknown",
            provider_watermark=None,
            observed_at=observed_at,
            expires_at=expires_at,
            evidence_refs=(),
            reason_codes=("owner-result-watermark-unobserved",),
        ),
        proof=CentralProofObservation(
            verdict="unknown",
            evidence=_link(
                state="unknown",
                observed_at=observed_at,
                expires_at=expires_at,
                reasons=("central-proof-unobserved",),
            ),
        ),
        acceptance=OwnerAcceptanceObservation(
            accepted=False,
            evidence=_link(
                state="unknown",
                observed_at=observed_at,
                expires_at=expires_at,
                reasons=("owner-acceptance-unobserved",),
            ),
        ),
        canary={
            "succeeded": False,
            "result_grounded": False,
            "canary_route": (
                target.canary_route
                if canary_purpose == "current"
                else f"{target.canary_route}/last-known-good"
            ),
            "canary_ref": None,
            "evidence": _link(
                state="unknown",
                observed_at=observed_at,
                expires_at=expires_at,
                reasons=("grounded-canary-unobserved",),
            ),
        },
        rollback=RollbackObservation(
            ready=False,
            rollback_route=target.rollback_route,
            evidence=_link(
                state="unknown",
                observed_at=observed_at,
                expires_at=expires_at,
                reasons=("rollback-proof-unobserved",),
            ),
        ),
    )


def _load_overlay(
    path: Path | None,
    *,
    allow_missing: bool,
    observed_at: datetime,
) -> tuple[RuntimeEvidenceOverlay | None, str]:
    if path is None:
        return None, "none"
    if not path.exists() and not path.is_symlink():
        if allow_missing:
            return None, "absent"
        raise ObservationProducerError("runtime evidence overlay is unavailable")
    payload, _ = _read_json(path, "runtime evidence overlay")
    _reject_secret_material(payload)
    try:
        overlay = RuntimeEvidenceOverlay.model_validate(payload)
    except ValidationError as exc:
        raise ObservationProducerError(
            "runtime evidence overlay failed contract validation"
        ) from exc
    if overlay.expires_at <= overlay.generated_at:
        raise ObservationProducerError(
            "runtime evidence overlay expiry must follow generation"
        )
    if overlay.generated_at > observed_at + MAX_OVERLAY_FUTURE_SKEW:
        raise ObservationProducerError(
            "runtime evidence overlay is causally future-dated"
        )
    overlay_digest = _digest(overlay.model_dump(mode="json"))
    if overlay.expires_at <= observed_at:
        return None, f"expired-{overlay_digest}"
    return overlay, overlay_digest


def _require_usable_issuer(
    link: LinkEvidence,
    owners: set[str],
    label: str,
) -> None:
    if link.state in {"exact", "compatible_drift"} and not any(
        ref.owner in owners for ref in link.evidence_refs
    ):
        raise ObservationProducerError(
            f"usable overlay {label} lacks evidence from its issuing owner"
        )


def _apply_overlay(
    subject: RuntimeSubject,
    overlay: RuntimeEvidenceOverlaySubject,
    target: RuntimeTarget,
) -> RuntimeSubject:
    if overlay.source is not None:
        _require_usable_issuer(
            overlay.source.evidence,
            {subject.owners.source_owner},
            "source",
        )
    if overlay.endpoint is not None:
        if (
            overlay.endpoint.transport != subject.endpoint.transport
            or overlay.endpoint.endpoint_ref != subject.endpoint.endpoint_ref
        ):
            raise ObservationProducerError(
                "runtime evidence overlay changed the committed endpoint target"
            )
        _require_usable_issuer(
            overlay.endpoint.evidence,
            {subject.owners.runtime_owner},
            "endpoint",
        )
    if overlay.freshness is not None and overlay.freshness.state in {
        "exact",
        "compatible_drift",
    }:
        if not any(
            ref.owner in {subject.owners.source_owner, subject.owners.access_owner}
            for ref in overlay.freshness.evidence_refs
        ):
            raise ObservationProducerError(
                "usable overlay freshness lacks owner-issued evidence"
            )
    if overlay.consumers is not None:
        for consumer in overlay.consumers:
            _require_usable_issuer(
                consumer.evidence,
                set(target.consumer_evidence_owners),
                "consumer",
            )
    if overlay.canary is not None:
        if overlay.canary.canary_route != subject.canary.canary_route:
            raise ObservationProducerError(
                "runtime evidence overlay changed the committed canary route"
            )
        _require_usable_issuer(
            overlay.canary.evidence,
            {subject.owners.runtime_owner},
            "canary",
        )
        if overlay.canary.succeeded:
            _require_usable_issuer(
                overlay.canary.evidence,
                {
                    subject.owners.source_owner,
                    subject.owners.acceptance_owner,
                },
                "canary owner grounding",
            )
    if (
        overlay.rollback is not None
        and overlay.rollback.rollback_route != subject.rollback.rollback_route
    ):
        raise ObservationProducerError(
            "runtime evidence overlay changed the committed rollback route"
        )
    updates: dict[str, Any] = {}
    for field_name in (
        "source",
        "endpoint",
        "consumers",
        "freshness",
        "proof",
        "acceptance",
        "canary",
        "rollback",
    ):
        value = getattr(overlay, field_name)
        if value is not None:
            updates[field_name] = value
    try:
        return RuntimeSubject.model_validate(
            {
                **subject.model_dump(mode="json"),
                **{
                    key: (
                        value.model_dump(mode="json")
                        if hasattr(value, "model_dump")
                        else [item.model_dump(mode="json") for item in value]
                        if isinstance(value, tuple)
                        else value
                    )
                    for key, value in updates.items()
                },
            }
        )
    except ValidationError as exc:
        raise ObservationProducerError(
            "runtime evidence overlay conflicts with the live subject"
        ) from exc


def produce_observation(
    *,
    deployment_manifest_path: Path = DEFAULT_DEPLOYMENT_MANIFEST_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    targets_path: Path = DEFAULT_TARGETS_PATH,
    overlay_path: Path | None = DEFAULT_OVERLAY_PATH,
    allow_missing_overlay: bool = True,
    canary_purpose: ObservationCanaryPurpose = "current",
    ttl_seconds: int = 300,
    clock: Callable[[], datetime] = _now,
    systemctl_runner: SystemctlRunner = _systemctl,
) -> tuple[RuntimeObservation, str]:
    if not 30 <= ttl_seconds <= 3600:
        raise ObservationProducerError("observation TTL must be 30..3600 seconds")
    observed_at = clock().astimezone(timezone.utc)
    expires_at = observed_at + timedelta(seconds=ttl_seconds)
    catalog, catalog_digest = _load_targets(targets_path)
    manifest, manifest_digest = _load_deployment(deployment_manifest_path)
    registry, registry_digest = _load_registry(registry_path)
    overlay, overlay_digest = _load_overlay(
        overlay_path,
        allow_missing=allow_missing_overlay,
        observed_at=observed_at,
    )
    overlay_subjects = (
        {
            (subject.organ_id, subject.policy_family): subject
            for subject in overlay.subjects
        }
        if overlay is not None
        else {}
    )
    subjects: list[RuntimeSubject] = []
    for target in catalog.targets:
        if not _registry_declares_target(registry, target):
            continue
        subject = _build_subject(
            target,
            manifest=manifest,
            registry=registry,
            registry_digest=registry_digest,
            observed_at=observed_at,
            expires_at=expires_at,
            runner=systemctl_runner,
            canary_purpose=canary_purpose,
        )
        overlay_subject = overlay_subjects.pop(
            (target.organ_id, target.policy_family),
            None,
        )
        if overlay_subject is not None:
            subject = _apply_overlay(subject, overlay_subject, target)
        subjects.append(subject)
    if overlay_subjects:
        raise ObservationProducerError(
            "runtime evidence overlay contains an unknown organ/policy target"
        )
    watermark = (
        f"deployment:{manifest_digest};registry:{registry_digest};"
        f"targets:{catalog_digest};overlay:{overlay_digest};"
        "legacy-shared-contours:excluded"
    )
    try:
        observation = RuntimeObservation(
            provider_watermark=watermark,
            generated_at=observed_at,
            expires_at=expires_at,
            subjects=tuple(subjects),
        )
    except ValidationError as exc:
        raise ObservationProducerError(
            "produced runtime observation failed contract validation"
        ) from exc
    payload = observation.model_dump(mode="json")
    _reject_secret_material(payload)
    _write_atomic(output_path, payload)
    return observation, _digest(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deployment-manifest",
        type=Path,
        default=DEFAULT_DEPLOYMENT_MANIFEST_PATH,
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY_PATH)
    parser.add_argument("--require-overlay", action="store_true")
    parser.add_argument(
        "--canary-purpose",
        choices=("current", "last-known-good"),
        default="current",
        help=(
            "select the committed current or distinct last-known-good canary "
            "route expected in the overlay"
        ),
    )
    parser.add_argument("--ttl-seconds", type=int, default=300)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        observation, digest = produce_observation(
            deployment_manifest_path=args.deployment_manifest,
            registry_path=args.registry,
            output_path=args.output,
            targets_path=args.targets,
            overlay_path=args.overlay,
            allow_missing_overlay=not args.require_overlay,
            canary_purpose=args.canary_purpose,
            ttl_seconds=args.ttl_seconds,
        )
    except ObservationProducerError as exc:
        print(f"abyss-stack MCP observation producer: {exc}", file=os.sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "schema_version": observation.schema_version,
                "observation_digest": digest,
                "generated_at": observation.generated_at.isoformat(),
                "expires_at": observation.expires_at.isoformat(),
                "subject_count": len(observation.subjects),
                "output": str(args.output),
                "claim_limit": (
                    "This receipt proves only successful composition of the "
                    "explicit deployment, registry, systemd, target, and optional "
                    "overlay inputs. Unknown owner evidence remains unknown."
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
