"""Host persistence for the SDK-owned cross-organ orchestration contract.

This module never invokes an owner MCP tool.  It issues the host-visible
receipt around one already-produced owner stage packet, delegates all chain
semantics to the explicit aoa-sdk CLI, and persists immutable private
snapshots for bounded stack inspection.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import shlex
import stat
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from ._runtime_config import PATH_CONFIG
from .contracts import Digest, EvidenceRef, Identifier, NonEmpty, StrictModel


DEFAULT_RUN_ROOT = PATH_CONFIG.stack_orchestration_root()
DEFAULT_SDK_ROOT = PATH_CONFIG.workspace_root()
MAX_INPUT_BYTES = 2 * 1024 * 1024
ZERO_DIGEST = "sha256:" + ("0" * 64)
StageKind = Literal[
    "kag_evidence",
    "memo_candidate",
    "eval_request",
    "eval_result",
    "owner_acceptance",
]
ArtifactRefKind = Literal[
    "orchestration_intent",
    "kag_evidence",
    "memo_candidate",
    "eval_request",
    "eval_result",
    "owner_acceptance",
]
TransitionState = Literal[
    "proceed",
    "stopped",
    "denied",
    "accepted_terminal",
    "rejected_terminal",
]


class CrossOrganHostError(ValueError):
    """A private orchestration input, SDK call, or stored record is invalid."""


class OrchestrationSchemaIdentity(StrictModel):
    """SDK-compatible owner schema identity used at the host boundary."""

    owner: NonEmpty
    schema_ref: NonEmpty
    schema_digest: Digest
    source_revision: NonEmpty
    schema_version: NonEmpty


class OrchestrationArtifactRef(StrictModel):
    """SDK-compatible typed artifact reference without importing aoa-sdk."""

    ref_kind: ArtifactRefKind
    owner: NonEmpty
    artifact_ref: NonEmpty
    artifact_digest: Digest
    source_revision: NonEmpty
    schema_identity: OrchestrationSchemaIdentity
    authority_ceiling: Literal[
        "read",
        "candidate",
        "internal_effect",
        "external_effect",
    ]
    created_at: datetime
    expires_at: datetime | None = None

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("artifact timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_identity(self) -> OrchestrationArtifactRef:
        if self.schema_identity.owner != self.owner:
            raise ValueError("artifact and schema owner must match")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("artifact expiry must follow creation")
        return self


class OwnerStagePacket(StrictModel):
    """Owner-produced stage facts before the stack issues its host receipt."""

    schema_version: Literal["abyss_stack_owner_stage_packet_v1"] = (
        "abyss_stack_owner_stage_packet_v1"
    )
    stage_kind: StageKind
    stage_owner: NonEmpty
    source_revision: NonEmpty
    output_ref: OrchestrationArtifactRef
    output_schema_identity: OrchestrationSchemaIdentity
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1)
    freshness_state: Literal[
        "exact",
        "compatible_drift",
        "stale_readable",
        "blocked",
        "unknown",
        "rollback_required",
    ]
    observed_at: datetime
    expires_at: datetime
    authority_ceiling: Literal[
        "read",
        "candidate",
        "internal_effect",
        "external_effect",
    ]
    effect_class: Literal[
        "observe",
        "derive",
        "validate",
        "prepare_candidate",
        "apply_runtime",
        "accept_source",
        "external_emit",
        "external_change",
    ]
    applied_state: Literal[
        "not_applied",
        "candidate_only",
        "applied",
        "denied",
    ]
    next_owner: NonEmpty | None
    transition_state: TransitionState
    stop_reason_codes: tuple[Identifier, ...] = ()
    review_ref: EvidenceRef | None = None
    acceptance_decision: Literal["accepted", "rejected"] | None = None
    owner_receipt_refs: tuple[OrchestrationArtifactRef, ...] = ()

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("owner stage timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_packet(self) -> OwnerStagePacket:
        if self.expires_at <= self.observed_at:
            raise ValueError("owner stage expiry must follow observation")
        terminal = self.transition_state != "proceed"
        if terminal and self.next_owner is not None:
            raise ValueError("terminal owner stage packet cannot name a next owner")
        if not terminal and self.next_owner is None:
            raise ValueError("proceeding owner stage packet requires next owner")
        if self.stage_owner != self.output_ref.owner:
            raise ValueError("stage owner must own the output artifact")
        if self.source_revision != self.output_ref.source_revision:
            raise ValueError(
                "stage source revision must match the output artifact"
            )
        if self.output_schema_identity != self.output_ref.schema_identity:
            raise ValueError(
                "output schema identity must match the output artifact"
            )
        if self.authority_ceiling != self.output_ref.authority_ceiling:
            raise ValueError(
                "stage authority ceiling must match the output artifact"
            )
        return self


class CrossOrganRuntimeRecord(StrictModel):
    """Stack-owned private index over one SDK-validated immutable snapshot."""

    schema_version: Literal["abyss_stack_cross_organ_runtime_record_v1"] = (
        "abyss_stack_cross_organ_runtime_record_v1"
    )
    record_id: Digest
    issuer: Literal["abyss-stack"] = "abyss-stack"
    control_owner: Literal["aoa-sdk"] = "aoa-sdk"
    runtime_owner: Literal["abyss-stack"] = "abyss-stack"
    run_id: Digest
    snapshot_digest: Digest
    snapshot_file_digest: Digest
    snapshot_ref: NonEmpty
    state: Literal[
        "awaiting_kag_evidence",
        "awaiting_memo_candidate",
        "awaiting_eval_request",
        "awaiting_eval_result",
        "awaiting_owner_acceptance",
        "accepted",
        "rejected",
        "stopped",
        "denied",
    ]
    stage_count: int = Field(ge=0, le=5)
    next_stage_kind: StageKind | None
    next_owner: NonEmpty | None
    host_id: Identifier
    request_expires_at: datetime
    persisted_at: datetime
    sdk_validation: dict[str, Any]
    latest_host_receipt_ref: NonEmpty | None = None
    contains_secrets: Literal[False] = False
    owner_tools_executed_by_stack: Literal[False] = False
    owner_tools_executed_by_sdk: Literal[False] = False
    proof_computed_by_stack: Literal[False] = False
    acceptance_inferred_by_stack: Literal[False] = False
    runtime_execution_authorized: Literal[False] = False
    claim_limit: Literal[
        "This record proves private host persistence of one aoa-sdk-validated "
        "cross-organ snapshot only. It does not prove owner invocation, "
        "grounding, benefit, acceptance, admission, or rollback."
    ] = (
        "This record proves private host persistence of one aoa-sdk-validated "
        "cross-organ snapshot only. It does not prove owner invocation, "
        "grounding, benefit, acceptance, admission, or rollback."
    )

    @field_validator("request_expires_at", "persisted_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("runtime record timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class SDKCommandResult:
    returncode: int
    stdout: str
    stderr: str


SDKRunner = Callable[[tuple[str, ...], Path], SDKCommandResult]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _clock_time(
    clock: Callable[[], datetime],
    label: str,
) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise CrossOrganHostError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _require_no_symlink_components(path: Path, label: str) -> Path:
    absolute = path.expanduser().absolute()
    for component in tuple(reversed(absolute.parents)) + (absolute,):
        if (component.exists() or component.is_symlink()) and component.is_symlink():
            raise CrossOrganHostError(f"{label} cannot traverse a symlink")
    return absolute


def _ensure_private_directory(path: Path) -> Path:
    absolute = _require_no_symlink_components(path, "orchestration directory")
    missing: list[Path] = []
    cursor = absolute
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
    if not absolute.is_dir() or absolute.is_symlink():
        raise CrossOrganHostError(
            "orchestration directory must be a non-symlink directory"
        )
    if stat.S_IMODE(absolute.stat().st_mode) & 0o077:
        raise CrossOrganHostError(
            "orchestration directory must not be group/world accessible"
        )
    return absolute


def _read_json(
    path: Path,
    label: str,
    *,
    require_private: bool,
) -> dict[str, Any]:
    selected = _require_no_symlink_components(path, label)
    try:
        descriptor = os.open(
            selected,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise CrossOrganHostError(
                    f"{label} must be a regular non-symlink file"
                )
            if require_private and stat.S_IMODE(metadata.st_mode) & 0o077:
                raise CrossOrganHostError(
                    f"{label} must not be group/world accessible"
                )
            if metadata.st_size > MAX_INPUT_BYTES:
                raise CrossOrganHostError(f"{label} exceeds its size limit")
            chunks: list[bytes] = []
            remaining = MAX_INPUT_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise CrossOrganHostError(
                f"{label} must be a regular non-symlink file"
            ) from exc
        raise CrossOrganHostError(f"{label} is unavailable") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise CrossOrganHostError(f"{label} exceeds its size limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise CrossOrganHostError(f"{label} is malformed JSON") from None
    if not isinstance(value, dict):
        raise CrossOrganHostError(f"{label} must contain a JSON object")
    _reject_secrets(value)
    return value


def _reject_secrets(value: dict[str, Any]) -> None:
    # Reuse the stack-wide reference-aware detector without creating a module
    # import cycle while core imports this store.
    from .core import _reject_secret_material

    _reject_secret_material(value)


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    destination = _require_no_symlink_components(path, "orchestration output")
    parent = _ensure_private_directory(destination.parent)
    if destination.exists() and (
        destination.is_symlink() or not destination.is_file()
    ):
        raise CrossOrganHostError(
            "orchestration output must be a regular non-symlink file"
        )
    rendered = (
        json.dumps(
            value,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if len(rendered) > MAX_INPUT_BYTES:
        raise CrossOrganHostError("orchestration output exceeds its size limit")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _default_runner(command: tuple[str, ...], cwd: Path) -> SDKCommandResult:
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "LANG", "LC_ALL", "PATH", "TZ"}
    }
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    return SDKCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


@contextmanager
def _exclusive_lock(root: Path) -> Iterator[None]:
    directory = _ensure_private_directory(root)
    lock_path = directory / ".host.lock"
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CrossOrganHostError(
                "orchestration lock must be a regular file"
            )
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


class CrossOrganRunStore:
    """Read and validate private content-addressed orchestration records."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = root or os.environ.get("ABYSS_STACK_ORCHESTRATION_ROOT")
        self.root = Path(configured or DEFAULT_RUN_ROOT).expanduser()

    def inspect(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id is None:
            record_path = self.root / "current.json"
        else:
            record_path = (
                self.root
                / _digest_component(run_id, "run id")
                / "current.json"
            )
        record_payload = _read_json(
            record_path,
            "orchestration runtime record",
            require_private=True,
        )
        try:
            record = CrossOrganRuntimeRecord.model_validate(record_payload)
        except ValidationError as exc:
            raise CrossOrganHostError(
                "orchestration runtime record failed contract validation"
            ) from exc
        body = record.model_dump(mode="json", exclude={"record_id"})
        if record.record_id != _digest(body):
            raise CrossOrganHostError("orchestration runtime record digest mismatch")
        if run_id is not None and record.run_id != _normalize_digest(run_id, "run id"):
            raise CrossOrganHostError("orchestration runtime record run mismatch")
        snapshot_path = self.root / record.snapshot_ref
        snapshot = _read_json(
            snapshot_path,
            "orchestration SDK snapshot",
            require_private=True,
        )
        if _digest(snapshot) != record.snapshot_file_digest:
            raise CrossOrganHostError("orchestration SDK snapshot file drifted")
        if (
            snapshot.get("run_id") != record.run_id
            or snapshot.get("snapshot_digest") != record.snapshot_digest
            or snapshot.get("state") != record.state
            or len(snapshot.get("stages", [])) != record.stage_count
        ):
            raise CrossOrganHostError(
                "orchestration SDK snapshot no longer matches its runtime record"
            )
        return {
            "schema": "abyss_stack_cross_organ_inspection_v1",
            "run_id": record.run_id,
            "snapshot_digest": record.snapshot_digest,
            "state": record.state,
            "stage_count": record.stage_count,
            "next_stage_kind": record.next_stage_kind,
            "next_owner": record.next_owner,
            "host_id": record.host_id,
            "request_expires_at": record.request_expires_at.isoformat().replace(
                "+00:00",
                "Z",
            ),
            "persisted_at": record.persisted_at.isoformat().replace(
                "+00:00",
                "Z",
            ),
            "sdk_validation": record.sdk_validation,
            "latest_host_receipt_ref": record.latest_host_receipt_ref,
            "snapshot_ref": record.snapshot_ref,
            "snapshot_file_digest": record.snapshot_file_digest,
            "contains_secrets": False,
            "owner_tools_executed_by_stack": False,
            "owner_tools_executed_by_sdk": False,
            "proof_computed_by_stack": False,
            "acceptance_inferred_by_stack": False,
            "runtime_execution_authorized": False,
            "claim_limit": record.claim_limit,
        }


class CrossOrganHost:
    """Issue host receipts, invoke the exact SDK contract, and persist output."""

    def __init__(
        self,
        *,
        run_root: str | Path,
        sdk_command: tuple[str, ...],
        sdk_root: str | Path = DEFAULT_SDK_ROOT,
        runner: SDKRunner = _default_runner,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        if not sdk_command or any(not item for item in sdk_command):
            raise CrossOrganHostError("an explicit SDK command is required")
        self.run_root = Path(run_root).expanduser()
        self.sdk_command = sdk_command
        self.sdk_root = Path(sdk_root).expanduser().resolve()
        self.runner = runner
        self.clock = clock

    def start(self, request_path: str | Path) -> CrossOrganRuntimeRecord:
        request = Path(request_path).expanduser()
        _read_json(
            request,
            "orchestration request",
            require_private=True,
        )
        with _exclusive_lock(self.run_root):
            with tempfile.TemporaryDirectory(
                prefix=".orchestration-start.",
                dir=_ensure_private_directory(self.run_root),
            ) as temporary:
                output = Path(temporary) / "run.json"
                self._invoke(
                    (
                        "organs",
                        "orchestration-start",
                        str(request.absolute()),
                        "--root",
                        str(self.sdk_root),
                        "--output",
                        str(output),
                    ),
                    "orchestration start",
                )
                run = _read_json(
                    output,
                    "SDK orchestration start output",
                    require_private=False,
                )
                validation = self._validate_sdk_run(output)
                return self._persist(
                    run,
                    validation=validation,
                    latest_receipt=None,
                )

    def advance(
        self,
        run_id: str,
        owner_stage_packet_path: str | Path,
    ) -> CrossOrganRuntimeRecord:
        normalized_run_id = _normalize_digest(run_id, "run id")
        packet_payload = _read_json(
            Path(owner_stage_packet_path).expanduser(),
            "owner stage packet",
            require_private=True,
        )
        try:
            packet = OwnerStagePacket.model_validate(packet_payload)
        except ValidationError as exc:
            raise CrossOrganHostError(
                "owner stage packet failed contract validation"
            ) from exc
        with _exclusive_lock(self.run_root):
            current_record = CrossOrganRunStore(self.run_root).inspect(
                normalized_run_id
            )
            current_snapshot = self.run_root / str(
                current_record["snapshot_ref"]
            )
            run = _read_json(
                current_snapshot,
                "current orchestration SDK snapshot",
                require_private=True,
            )
            observation, receipt = self._build_observation(run, packet)
            with tempfile.TemporaryDirectory(
                prefix=".orchestration-advance.",
                dir=_ensure_private_directory(self.run_root),
            ) as temporary:
                temp_root = Path(temporary)
                observation_path = temp_root / "observation.json"
                output = temp_root / "run.json"
                _write_private_json(observation_path, observation)
                self._invoke(
                    (
                        "organs",
                        "orchestration-advance",
                        str(current_snapshot),
                        str(observation_path),
                        "--root",
                        str(self.sdk_root),
                        "--output",
                        str(output),
                    ),
                    "orchestration advance",
                )
                updated = _read_json(
                    output,
                    "SDK orchestration advance output",
                    require_private=False,
                )
                validation = self._validate_sdk_run(output)
                return self._persist(
                    updated,
                    validation=validation,
                    latest_receipt=receipt,
                )

    def validate(self, run_id: str) -> dict[str, Any]:
        inspected = CrossOrganRunStore(self.run_root).inspect(run_id)
        snapshot = self.run_root / str(inspected["snapshot_ref"])
        return self._validate_sdk_run(snapshot)

    def _invoke(self, arguments: tuple[str, ...], label: str) -> SDKCommandResult:
        result = self.runner((*self.sdk_command, *arguments), self.sdk_root)
        if result.returncode != 0:
            raise CrossOrganHostError(
                f"{label} failed in the explicit SDK "
                f"(return code {result.returncode})"
            )
        return result

    def _validate_sdk_run(self, run_path: Path) -> dict[str, Any]:
        result = self._invoke(
            (
                "organs",
                "orchestration-validate",
                str(run_path),
                "--root",
                str(self.sdk_root),
            ),
            "orchestration validation",
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise CrossOrganHostError(
                "SDK validation returned malformed output"
            ) from None
        if (
            not isinstance(payload, dict)
            or payload.get("valid") is not True
            or payload.get("owner_tools_executed_by_sdk") is not False
            or payload.get("proof_computed_by_sdk") is not False
            or payload.get("durable_memory_written_by_sdk") is not False
            or payload.get("acceptance_inferred_by_sdk") is not False
        ):
            raise CrossOrganHostError(
                "SDK validation did not preserve orchestration stop lines"
            )
        _reject_secrets(payload)
        return payload

    def _build_observation(
        self,
        run: dict[str, Any],
        packet: OwnerStagePacket,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        stages = run.get("stages")
        request = run.get("request")
        if not isinstance(stages, list) or not isinstance(request, dict):
            raise CrossOrganHostError("current SDK run has an invalid shape")
        contracts = request.get("stage_contracts")
        if not isinstance(contracts, list) or len(stages) >= len(contracts):
            raise CrossOrganHostError("current SDK run has no remaining stage")
        contract = contracts[len(stages)]
        if not isinstance(contract, dict):
            raise CrossOrganHostError("current SDK stage contract is invalid")
        if (
            packet.stage_kind != run.get("next_stage_kind")
            or packet.stage_owner != run.get("next_owner")
            or packet.stage_kind != contract.get("stage_kind")
            or packet.stage_owner != contract.get("owner")
        ):
            raise CrossOrganHostError(
                "owner stage packet does not match the next SDK owner contract"
            )
        input_ref = (
            request.get("root_input")
            if not stages
            else stages[-1].get("observation", {}).get("output_ref")
        )
        if not isinstance(input_ref, dict):
            raise CrossOrganHostError("current SDK run input ref is invalid")
        issued_at = _clock_time(self.clock, "orchestration host clock")
        if issued_at < packet.observed_at or issued_at >= packet.expires_at:
            raise CrossOrganHostError(
                "host receipt time is outside the owner stage lifetime"
            )
        output_ref = packet.output_ref.model_dump(mode="json")
        output_schema_identity = packet.output_schema_identity.model_dump(
            mode="json"
        )
        evidence_refs = [
            item.model_dump(mode="json") for item in packet.evidence_refs
        ]
        owner_receipt_refs = [
            item.model_dump(mode="json")
            for item in packet.owner_receipt_refs
        ]
        review_ref = (
            packet.review_ref.model_dump(mode="json")
            if packet.review_ref is not None
            else None
        )
        output_digest = output_ref.get("artifact_digest")
        input_digest = input_ref.get("artifact_digest")
        if (
            not isinstance(output_digest, str)
            or not isinstance(input_digest, str)
        ):
            raise CrossOrganHostError("stage artifact digests are missing")
        outcome = _receipt_outcome(packet.stage_kind, packet.transition_state)
        seed = {
            "run_id": run.get("run_id"),
            "previous_snapshot_digest": run.get("snapshot_digest"),
            "stage_kind": packet.stage_kind,
            "output_artifact_digest": output_digest,
            "issued_at": issued_at.isoformat(),
        }
        receipt_id = "host-" + _digest(seed).removeprefix("sha256:")[:32]
        receipt: dict[str, Any] = {
            "schema_version": "aoa_host_stage_receipt_v1",
            "receipt_id": receipt_id,
            "receipt_ref": f"orchestration://host-receipt/{receipt_id}",
            "host_id": request.get("host_id"),
            "run_id": run.get("run_id"),
            "stage_kind": packet.stage_kind,
            "previous_snapshot_digest": run.get("snapshot_digest"),
            "input_artifact_digest": input_digest,
            "output_artifact_digest": output_digest,
            "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
            "outcome": outcome,
            "owner_receipt_refs": owner_receipt_refs,
        }
        receipt["receipt_digest"] = _digest(receipt)
        observation = {
            "stage_kind": packet.stage_kind,
            "stage_owner": packet.stage_owner,
            "source_revision": packet.source_revision,
            "input_ref": input_ref,
            "output_ref": output_ref,
            "input_schema_identity": input_ref.get("schema_identity"),
            "output_schema_identity": output_schema_identity,
            "evidence_refs": evidence_refs,
            "freshness_state": packet.freshness_state,
            "observed_at": packet.observed_at.isoformat().replace("+00:00", "Z"),
            "expires_at": packet.expires_at.isoformat().replace("+00:00", "Z"),
            "authority_ceiling": packet.authority_ceiling,
            "effect_class": packet.effect_class,
            "applied_state": packet.applied_state,
            "receipt": receipt,
            "next_owner": packet.next_owner,
            "transition_state": packet.transition_state,
            "stop_reason_codes": list(packet.stop_reason_codes),
            "review_ref": review_ref,
            "acceptance_decision": packet.acceptance_decision,
            "mcp_tools_executed_by_sdk": False,
            "model_confidence_is_acceptance_authority": False,
        }
        _reject_secrets(observation)
        return observation, receipt

    def _persist(
        self,
        run: dict[str, Any],
        *,
        validation: dict[str, Any],
        latest_receipt: dict[str, Any] | None,
    ) -> CrossOrganRuntimeRecord:
        run_id = _normalize_digest(run.get("run_id"), "SDK run id")
        snapshot_digest = _normalize_digest(
            run.get("snapshot_digest"),
            "SDK snapshot digest",
        )
        run_component = _digest_component(run_id, "SDK run id")
        snapshot_component = _digest_component(
            snapshot_digest,
            "SDK snapshot digest",
        )
        request = run.get("request")
        stages = run.get("stages")
        if not isinstance(request, dict) or not isinstance(stages, list):
            raise CrossOrganHostError("SDK orchestration output has an invalid shape")
        request_expires_at = _parse_time(
            request.get("expires_at"),
            "request expires_at",
        )
        host_id = request.get("host_id")
        if not isinstance(host_id, str):
            raise CrossOrganHostError("SDK orchestration output has no host id")
        state = run.get("state")
        next_stage = run.get("next_stage_kind")
        next_owner = run.get("next_owner")
        snapshot_ref = (
            Path(run_component)
            / "snapshots"
            / f"{snapshot_component}.json"
        )
        snapshot_path = self.run_root / snapshot_ref
        snapshot_file_digest = _digest(run)
        if snapshot_path.exists():
            existing = _read_json(
                snapshot_path,
                "existing orchestration SDK snapshot",
                require_private=True,
            )
            if existing != run:
                raise CrossOrganHostError(
                    "immutable orchestration SDK snapshot collision"
                )
        else:
            _write_private_json(snapshot_path, run)
        latest_receipt_ref: str | None = None
        if latest_receipt is not None:
            receipt_id = latest_receipt.get("receipt_id")
            if not isinstance(receipt_id, str):
                raise CrossOrganHostError("host receipt identity is missing")
            receipt_ref = (
                Path(run_component)
                / "receipts"
                / f"{receipt_id}.json"
            )
            receipt_path = self.run_root / receipt_ref
            if receipt_path.exists():
                existing_receipt = _read_json(
                    receipt_path,
                    "existing host receipt",
                    require_private=True,
                )
                if existing_receipt != latest_receipt:
                    raise CrossOrganHostError("immutable host receipt collision")
            else:
                _write_private_json(receipt_path, latest_receipt)
            latest_receipt_ref = receipt_ref.as_posix()
        body = {
            "schema_version": "abyss_stack_cross_organ_runtime_record_v1",
            "issuer": "abyss-stack",
            "control_owner": "aoa-sdk",
            "runtime_owner": "abyss-stack",
            "run_id": run_id,
            "snapshot_digest": snapshot_digest,
            "snapshot_file_digest": snapshot_file_digest,
            "snapshot_ref": snapshot_ref.as_posix(),
            "state": state,
            "stage_count": len(stages),
            "next_stage_kind": next_stage,
            "next_owner": next_owner,
            "host_id": host_id,
            "request_expires_at": request_expires_at.isoformat(),
            "persisted_at": _clock_time(
                self.clock,
                "orchestration host clock",
            ).isoformat(),
            "sdk_validation": validation,
            "latest_host_receipt_ref": latest_receipt_ref,
            "contains_secrets": False,
            "owner_tools_executed_by_stack": False,
            "owner_tools_executed_by_sdk": False,
            "proof_computed_by_stack": False,
            "acceptance_inferred_by_stack": False,
            "runtime_execution_authorized": False,
            "claim_limit": (
                "This record proves private host persistence of one "
                "aoa-sdk-validated cross-organ snapshot only. It does not "
                "prove owner invocation, grounding, benefit, acceptance, "
                "admission, or rollback."
            ),
        }
        try:
            placeholder = CrossOrganRuntimeRecord.model_validate(
                {"record_id": ZERO_DIGEST, **body}
            )
            record = placeholder.model_copy(
                update={
                    "record_id": _digest(
                        placeholder.model_dump(
                            mode="json",
                            exclude={"record_id"},
                        )
                    )
                }
            )
        except ValidationError as exc:
            raise CrossOrganHostError(
                "SDK orchestration output cannot form a runtime record"
            ) from exc
        record_payload = record.model_dump(mode="json")
        record_path = (
            self.run_root
            / run_component
            / "records"
            / f"{record.record_id.removeprefix('sha256:')}.json"
        )
        if record_path.exists():
            existing_record = _read_json(
                record_path,
                "existing orchestration runtime record",
                require_private=True,
            )
            if existing_record != record_payload:
                raise CrossOrganHostError(
                    "immutable orchestration runtime record collision"
                )
        else:
            _write_private_json(record_path, record_payload)
        _write_private_json(
            self.run_root / run_component / "current.json",
            record_payload,
        )
        _write_private_json(self.run_root / "current.json", record_payload)
        return record


def _normalize_digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise CrossOrganHostError(f"{label} must be a SHA-256 digest")
    return value


def _digest_component(value: object, label: str) -> str:
    return _normalize_digest(value, label).removeprefix("sha256:")


def _parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise CrossOrganHostError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CrossOrganHostError(f"{label} must be a timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CrossOrganHostError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _receipt_outcome(
    stage_kind: StageKind,
    transition_state: TransitionState,
) -> str:
    if transition_state == "stopped":
        return "stopped"
    if transition_state == "denied":
        return "denied"
    if transition_state == "accepted_terminal":
        return "accepted"
    if transition_state == "rejected_terminal":
        return "rejected"
    return {
        "kag_evidence": "observed",
        "memo_candidate": "candidate_created",
        "eval_request": "request_created",
        "eval_result": "validated",
        "owner_acceptance": "accepted",
    }[stage_kind]


def _sdk_command(value: str) -> tuple[str, ...]:
    command = tuple(shlex.split(value))
    if not command:
        raise CrossOrganHostError("an explicit SDK command is required")
    return command


def main() -> None:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-orchestration")
    parser.add_argument(
        "--run-root",
        default=os.environ.get(
            "ABYSS_STACK_ORCHESTRATION_ROOT",
            str(DEFAULT_RUN_ROOT),
        ),
    )
    parser.add_argument(
        "--sdk-command",
        default=os.environ.get("AOA_SDK_ORCHESTRATION_COMMAND"),
        help="Exact aoa-sdk CLI command; required if the environment omits it.",
    )
    parser.add_argument("--sdk-root", default=str(DEFAULT_SDK_ROOT))
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start")
    start.add_argument("request")

    advance = commands.add_parser("advance")
    advance.add_argument("run_id")
    advance.add_argument("owner_stage_packet")

    inspect = commands.add_parser("inspect")
    inspect.add_argument("--run-id")

    validate = commands.add_parser("validate")
    validate.add_argument("run_id")

    args = parser.parse_args()
    try:
        if args.command == "inspect":
            result: Any = CrossOrganRunStore(args.run_root).inspect(args.run_id)
        else:
            if not args.sdk_command:
                raise CrossOrganHostError("an explicit SDK command is required")
            host = CrossOrganHost(
                run_root=args.run_root,
                sdk_command=_sdk_command(args.sdk_command),
                sdk_root=args.sdk_root,
            )
            if args.command == "start":
                result = host.start(args.request).model_dump(mode="json")
            elif args.command == "advance":
                result = host.advance(
                    args.run_id,
                    args.owner_stage_packet,
                ).model_dump(mode="json")
            else:
                result = host.validate(args.run_id)
    except CrossOrganHostError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
