"""Exact, approved restart-and-rollback pilot for the stack MCP read unit."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from .canary import CanaryReceipt, run_canary
from .contracts import Digest, Identifier, RuntimePlanCandidate, StrictModel
from .core import ObservationStore, StackMCPError, _reject_secret_material, canonical_json_bytes


EXACT_ORGAN_ID = "abyss-stack"
EXACT_POLICY_FAMILY = "read"
EXACT_UNIT_NAME = "abyss-stack-mcp-read.service"
EXACT_TOOL_ID = "stack_execute_approved_read_restart_pilot"
DEFAULT_EFFECT_ROOT = Path("/srv/AbyssOS/abyss-stack/Logs/mcp/internal-effects/read-restart-pilot")
DEFAULT_OBSERVATION_PATH = Path("/srv/AbyssOS/abyss-stack/Logs/mcp/observations/current.json")
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_EFFECT_ATTEMPTS_PER_MINUTE = 1
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
SystemctlRunner = Callable[[str], None]
SnapshotRunner = Callable[[], "ProcessSnapshot"]
CanaryRunner = Callable[[Path, str], tuple[CanaryReceipt, Path]]


class EffectError(StackMCPError):
    """Fail-closed effect error without request values or secrets."""


class EffectRecoveryError(EffectError):
    """An effect attempt ended with a persisted recovery receipt."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("effect timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


class InternalEffectApproval(StrictModel):
    schema_version: Literal["abyss_stack_internal_effect_approval_v1"] = (
        "abyss_stack_internal_effect_approval_v1"
    )
    approval_id: Digest
    plan_id: Digest
    action: Literal["restart_and_rollback_pilot"] = "restart_and_rollback_pilot"
    target_organ_id: Literal["abyss-stack"] = EXACT_ORGAN_ID
    target_policy_family: Literal["read"] = EXACT_POLICY_FAMILY
    exact_unit_name: Literal["abyss-stack-mcp-read.service"] = EXACT_UNIT_NAME
    approved_by: Identifier
    authorized_principal: Literal["abyss-stack-mcp-internal-effect-client"] = (
        "abyss-stack-mcp-internal-effect-client"
    )
    decision: Literal["approved"] = "approved"
    issued_at: datetime
    expires_at: datetime
    idempotency_key: Identifier
    source_to_sink_policy_ref: Literal[
        "owner://abyss-stack/internal-effect/read-restart-pilot-v1"
    ] = "owner://abyss-stack/internal-effect/read-restart-pilot-v1"
    human_approval: Literal[True] = True
    contains_secrets: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_approval(self) -> "InternalEffectApproval":
        if self.expires_at <= self.issued_at:
            raise ValueError("approval expiry must follow issuance")
        if self.approval_id != _digest(self.model_dump(mode="json", exclude={"approval_id"})):
            raise ValueError("approval_id must address the exact approval")
        return self


class ProcessSnapshot(StrictModel):
    schema_version: Literal["abyss_stack_internal_effect_process_snapshot_v1"] = (
        "abyss_stack_internal_effect_process_snapshot_v1"
    )
    unit_name: Literal["abyss-stack-mcp-read.service"] = EXACT_UNIT_NAME
    active_state: Literal["active"] = "active"
    sub_state: Literal["running"] = "running"
    main_pid: Annotated[int, Field(gt=0)]
    start_timestamp_monotonic: Annotated[int, Field(gt=0)]
    process_identity: str
    captured_at: datetime

    @field_validator("captured_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_identity(self) -> "ProcessSnapshot":
        expected = (
            f"systemd-user:{self.unit_name}:pid:{self.main_pid}:"
            f"start:{self.start_timestamp_monotonic}"
        )
        if self.process_identity != expected:
            raise ValueError("process identity does not match exact systemd fields")
        return self


class InternalEffectReceipt(StrictModel):
    schema_version: Literal["abyss_stack_internal_effect_receipt_v1"] = (
        "abyss_stack_internal_effect_receipt_v1"
    )
    receipt_id: Digest
    issuer: Literal["abyss-stack"] = "abyss-stack"
    tool_id: Literal["stack_execute_approved_read_restart_pilot"] = EXACT_TOOL_ID
    plan_id: Digest
    approval_id: Digest
    idempotency_key: Identifier
    target_organ_id: Literal["abyss-stack"] = EXACT_ORGAN_ID
    target_policy_family: Literal["read"] = EXACT_POLICY_FAMILY
    exact_unit_name: Literal["abyss-stack-mcp-read.service"] = EXACT_UNIT_NAME
    expected_observation_digest: Digest
    source_revision: str
    package_digest: Digest
    deployed_revision: str
    deployed_tree_digest: Digest
    pre_effect: ProcessSnapshot
    post_effect: ProcessSnapshot
    post_effect_canary_ref: str
    post_effect_canary_digest: Digest
    post_effect_canary_succeeded: Literal[True] = True
    rollback_target_process_identity: str
    rollback_executed: Literal[True] = True
    post_rollback: ProcessSnapshot
    post_rollback_canary_ref: str
    post_rollback_canary_digest: Digest
    post_rollback_canary_succeeded: Literal[True] = True
    outcome: Literal["succeeded_rolled_back"] = "succeeded_rolled_back"
    actual_effects: tuple[
        Literal["restart_exact_unit"], Literal["rollback_restart_exact_unit"]
    ] = ("restart_exact_unit", "rollback_restart_exact_unit")
    approval_verified: Literal[True] = True
    source_to_sink_policy_verified: Literal[True] = True
    runtime_effect_authorized: Literal[True] = True
    external_effect_authorized: Literal[False] = False
    observed_at: datetime
    contains_secrets: Literal[False] = False
    claim_limit: Literal[
        "This receipt proves one approved restart and one executed rollback restart "
        "of abyss-stack-mcp-read.service with authenticated post-effect and "
        "post-rollback canaries. It authorizes no other unit, command, source "
        "mutation, credential use, admission, or external effect."
    ] = (
        "This receipt proves one approved restart and one executed rollback restart "
        "of abyss-stack-mcp-read.service with authenticated post-effect and "
        "post-rollback canaries. It authorizes no other unit, command, source "
        "mutation, credential use, admission, or external effect."
    )

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_receipt(self) -> "InternalEffectReceipt":
        unsigned = self.model_dump(mode="json", exclude={"receipt_id"})
        if self.receipt_id != _digest(unsigned):
            raise ValueError("receipt_id must address the exact effect receipt")
        identities = {
            self.pre_effect.process_identity,
            self.post_effect.process_identity,
            self.post_rollback.process_identity,
        }
        if len(identities) != 3:
            raise ValueError("effect and rollback must each produce a new process identity")
        if self.rollback_target_process_identity != self.pre_effect.process_identity:
            raise ValueError("rollback target must bind the exact pre-effect process contour")
        return self


class InternalEffectDenialReceipt(StrictModel):
    schema_version: Literal["abyss_stack_internal_effect_denial_receipt_v1"] = (
        "abyss_stack_internal_effect_denial_receipt_v1"
    )
    receipt_id: Digest
    issuer: Literal["abyss-stack"] = "abyss-stack"
    tool_id: Literal["stack_execute_approved_read_restart_pilot"] = EXACT_TOOL_ID
    request_digest: Digest
    reason_code: Identifier
    effect_attempted: Literal[False] = False
    runtime_effect_authorized: Literal[False] = False
    external_effect_authorized: Literal[False] = False
    observed_at: datetime
    contains_secrets: Literal[False] = False

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_receipt(self) -> "InternalEffectDenialReceipt":
        if self.receipt_id != _digest(
            self.model_dump(mode="json", exclude={"receipt_id"})
        ):
            raise ValueError("receipt_id must address the exact denial receipt")
        return self


class InternalEffectRecoveryReceipt(StrictModel):
    schema_version: Literal["abyss_stack_internal_effect_recovery_receipt_v1"] = (
        "abyss_stack_internal_effect_recovery_receipt_v1"
    )
    receipt_id: Digest
    issuer: Literal["abyss-stack"] = "abyss-stack"
    tool_id: Literal["stack_execute_approved_read_restart_pilot"] = EXACT_TOOL_ID
    plan_id: Digest
    approval_id: Digest
    idempotency_key_digest: Digest
    exact_unit_name: Literal["abyss-stack-mcp-read.service"] = EXACT_UNIT_NAME
    effect_attempted: Literal[True] = True
    post_effect: ProcessSnapshot | None = None
    post_effect_canary_ref: str | None = None
    post_effect_canary_digest: Digest | None = None
    rollback_executed: Literal[True] = True
    rollback_succeeded: bool
    post_rollback: ProcessSnapshot | None = None
    post_rollback_canary_ref: str | None = None
    post_rollback_canary_digest: Digest | None = None
    outcome: Literal[
        "effect_failed_rollback_succeeded",
        "effect_failed_rollback_failed",
    ]
    reason_codes: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    runtime_effect_authorized: Literal[True] = True
    external_effect_authorized: Literal[False] = False
    observed_at: datetime
    contains_secrets: Literal[False] = False

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_receipt(self) -> "InternalEffectRecoveryReceipt":
        if self.receipt_id != _digest(
            self.model_dump(mode="json", exclude={"receipt_id"})
        ):
            raise ValueError("receipt_id must address the exact recovery receipt")
        if self.rollback_succeeded:
            if (
                self.outcome != "effect_failed_rollback_succeeded"
                or self.post_rollback is None
                or self.post_rollback_canary_ref is None
                or self.post_rollback_canary_digest is None
            ):
                raise ValueError("successful recovery requires rollback postconditions")
        elif self.outcome != "effect_failed_rollback_failed":
            raise ValueError("failed rollback requires the failed recovery outcome")
        return self


def _safe_root(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    for component in (*reversed(absolute.parents), absolute):
        if component.exists() and component.is_symlink():
            raise EffectError("effect root cannot traverse a symlink")
    absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not absolute.is_dir() or absolute.is_symlink():
        raise EffectError("effect root must be a non-symlink directory")
    if stat.S_IMODE(absolute.stat().st_mode) & 0o077:
        raise EffectError("effect root permissions are too broad")
    return absolute


def _write_private(path: Path, payload: dict[str, Any], *, replace: bool = False) -> None:
    _reject_secret_material(payload)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if replace else os.O_EXCL)
    descriptor = os.open(path, flags | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        raw = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_private(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise EffectError(f"{label} must be a regular non-symlink file")
    metadata = path.stat()
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise EffectError(f"{label} permissions are too broad")
    if metadata.st_size > MAX_ARTIFACT_BYTES:
        raise EffectError(f"{label} exceeds its size limit")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EffectError(f"{label} is invalid") from exc
    if not isinstance(payload, dict):
        raise EffectError(f"{label} must be an object")
    _reject_secret_material(payload)
    return payload


def _artifact_path(root: Path, district: str, digest: str) -> Path:
    suffix = digest.removeprefix("sha256:")
    if len(suffix) != 64 or any(char not in "0123456789abcdef" for char in suffix):
        raise EffectError("artifact digest is invalid")
    return root / district / f"{suffix}.json"


def _request_digest(plan_id: str, approval_id: str, idempotency_key: str) -> str:
    return _digest(
        {
            "plan_id": plan_id,
            "approval_id": approval_id,
            "idempotency_key_digest": _digest_bytes(idempotency_key.encode("utf-8")),
        }
    )


def _reason_code(error: BaseException) -> str:
    code = re.sub(r"[^a-z0-9]+", "_", str(error).lower()).strip("_")
    return (code or "internal_effect_failed")[:120]


def _write_denial_receipt(
    root: Path,
    *,
    plan_id: str,
    approval_id: str,
    idempotency_key: str,
    error: BaseException,
    observed_at: datetime,
) -> InternalEffectDenialReceipt:
    unsigned = {
        "schema_version": "abyss_stack_internal_effect_denial_receipt_v1",
        "issuer": "abyss-stack",
        "tool_id": EXACT_TOOL_ID,
        "request_digest": _request_digest(plan_id, approval_id, idempotency_key),
        "reason_code": _reason_code(error),
        "effect_attempted": False,
        "runtime_effect_authorized": False,
        "external_effect_authorized": False,
        "observed_at": _timestamp(observed_at),
        "contains_secrets": False,
    }
    receipt = InternalEffectDenialReceipt.model_validate(
        {"receipt_id": _digest(unsigned), **unsigned}
    )
    path = _artifact_path(root, "denial-receipts", receipt.receipt_id)
    if not path.exists():
        _write_private(path, receipt.model_dump(mode="json"))
    return receipt


def _write_recovery_receipt(
    root: Path,
    *,
    plan: RuntimePlanCandidate,
    approval: InternalEffectApproval,
    idempotency_key: str,
    post_effect: ProcessSnapshot | None,
    post_effect_canary_path: Path | None,
    rollback_succeeded: bool,
    post_rollback: ProcessSnapshot | None,
    post_rollback_canary_path: Path | None,
    reason_codes: tuple[str, ...],
    observed_at: datetime,
) -> InternalEffectRecoveryReceipt:
    unsigned = {
        "schema_version": "abyss_stack_internal_effect_recovery_receipt_v1",
        "issuer": "abyss-stack",
        "tool_id": EXACT_TOOL_ID,
        "plan_id": plan.plan_id,
        "approval_id": approval.approval_id,
        "idempotency_key_digest": _digest_bytes(idempotency_key.encode("utf-8")),
        "exact_unit_name": EXACT_UNIT_NAME,
        "effect_attempted": True,
        "post_effect": (
            post_effect.model_dump(mode="json") if post_effect is not None else None
        ),
        "post_effect_canary_ref": (
            post_effect_canary_path.as_posix()
            if post_effect_canary_path is not None
            else None
        ),
        "post_effect_canary_digest": (
            _digest_bytes(post_effect_canary_path.read_bytes())
            if post_effect_canary_path is not None
            else None
        ),
        "rollback_executed": True,
        "rollback_succeeded": rollback_succeeded,
        "post_rollback": (
            post_rollback.model_dump(mode="json")
            if post_rollback is not None
            else None
        ),
        "post_rollback_canary_ref": (
            post_rollback_canary_path.as_posix()
            if post_rollback_canary_path is not None
            else None
        ),
        "post_rollback_canary_digest": (
            _digest_bytes(post_rollback_canary_path.read_bytes())
            if post_rollback_canary_path is not None
            else None
        ),
        "outcome": (
            "effect_failed_rollback_succeeded"
            if rollback_succeeded
            else "effect_failed_rollback_failed"
        ),
        "reason_codes": list(reason_codes),
        "runtime_effect_authorized": True,
        "external_effect_authorized": False,
        "observed_at": _timestamp(observed_at),
        "contains_secrets": False,
    }
    receipt = InternalEffectRecoveryReceipt.model_validate(
        {"receipt_id": _digest(unsigned), **unsigned}
    )
    _write_private(
        _artifact_path(root, "recovery-receipts", receipt.receipt_id),
        receipt.model_dump(mode="json"),
    )
    return receipt


def _load_plan(root: Path, plan_id: str) -> RuntimePlanCandidate:
    try:
        return RuntimePlanCandidate.model_validate(
            _read_private(_artifact_path(root, "plans", plan_id), "effect plan")
        )
    except ValidationError as exc:
        raise EffectError("effect plan failed contract validation") from exc


def _load_approval(root: Path, approval_id: str) -> InternalEffectApproval:
    try:
        return InternalEffectApproval.model_validate(
            _read_private(_artifact_path(root, "approvals", approval_id), "effect approval")
        )
    except ValidationError as exc:
        raise EffectError("effect approval failed contract validation") from exc


def stage_plan(input_path: Path, effect_root: Path = DEFAULT_EFFECT_ROOT) -> Path:
    root = _safe_root(effect_root)
    try:
        plan = RuntimePlanCandidate.model_validate(_read_private(input_path, "candidate plan"))
    except ValidationError as exc:
        raise EffectError("candidate plan failed contract validation") from exc
    _validate_exact_plan_shape(plan)
    destination = _artifact_path(root, "plans", plan.plan_id)
    if destination.exists():
        existing = _load_plan(root, plan.plan_id)
        if existing != plan:
            raise EffectError("content-addressed plan collision")
        return destination
    _write_private(destination, plan.model_dump(mode="json"))
    return destination


def create_approval(
    *,
    plan_id: str,
    approved_by: str,
    idempotency_key: str,
    expires_at: datetime,
    effect_root: Path = DEFAULT_EFFECT_ROOT,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> tuple[InternalEffectApproval, Path]:
    root = _safe_root(effect_root)
    plan = _load_plan(root, plan_id)
    _validate_exact_plan_shape(plan)
    now = _utc(clock())
    expires = _utc(expires_at)
    if now >= plan.expires_at or expires > plan.expires_at or expires <= now:
        raise EffectError("approval must fit inside the live plan expiry")
    unsigned = {
        "schema_version": "abyss_stack_internal_effect_approval_v1",
        "plan_id": plan.plan_id,
        "action": "restart_and_rollback_pilot",
        "target_organ_id": EXACT_ORGAN_ID,
        "target_policy_family": EXACT_POLICY_FAMILY,
        "exact_unit_name": EXACT_UNIT_NAME,
        "approved_by": approved_by,
        "authorized_principal": "abyss-stack-mcp-internal-effect-client",
        "decision": "approved",
        "issued_at": _timestamp(now),
        "expires_at": _timestamp(expires),
        "idempotency_key": idempotency_key,
        "source_to_sink_policy_ref": "owner://abyss-stack/internal-effect/read-restart-pilot-v1",
        "human_approval": True,
        "contains_secrets": False,
    }
    approval = InternalEffectApproval.model_validate({"approval_id": _digest(unsigned), **unsigned})
    path = _artifact_path(root, "approvals", approval.approval_id)
    if not path.exists():
        _write_private(path, approval.model_dump(mode="json"))
    return approval, path


def _validate_exact_plan_shape(plan: RuntimePlanCandidate) -> None:
    if (
        plan.plan_kind != "restart"
        or plan.target_organ_id != EXACT_ORGAN_ID
        or plan.target_policy_family != EXACT_POLICY_FAMILY
        or plan.exact_unit_name != EXACT_UNIT_NAME
        or plan.execution_authorized is not False
        or plan.approval_required_before_execution is not True
    ):
        raise EffectError("plan is outside the exact restart pilot contour")
    actions = [(step.action, step.exact_target) for step in plan.steps]
    required = [
        ("snapshot-exact-process", EXACT_UNIT_NAME),
        ("restart-exact-unit", EXACT_UNIT_NAME),
    ]
    if not all(item in actions for item in required):
        raise EffectError("plan does not contain the exact restart steps")


def _claim_rate_slot(
    root: Path,
    *,
    plan_id: str,
    approval_id: str,
    idempotency_key: str,
    observed_at: datetime,
) -> None:
    attempts_root = root / "attempt-receipts"
    attempts_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    attempts_root.chmod(0o700)
    window_start = observed_at - timedelta(minutes=1)
    recent = 0
    paths = sorted(attempts_root.glob("*.json"))
    if len(paths) > 1024:
        raise EffectError("internal-effect attempt journal exceeds its bound")
    for path in paths:
        payload = _read_private(path, "effect attempt receipt")
        try:
            timestamp = _utc(datetime.fromisoformat(str(payload["observed_at"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise EffectError("effect attempt receipt is invalid") from exc
        if window_start <= timestamp <= observed_at:
            recent += 1
    if recent >= MAX_EFFECT_ATTEMPTS_PER_MINUTE:
        raise EffectError("internal-effect start rate limit exceeded")
    unsigned = {
        "schema_version": "abyss_stack_internal_effect_attempt_receipt_v1",
        "request_digest": _request_digest(plan_id, approval_id, idempotency_key),
        "observed_at": _timestamp(observed_at),
        "contains_secrets": False,
    }
    unsigned["receipt_id"] = _digest(unsigned)
    _write_private(
        _artifact_path(root, "attempt-receipts", unsigned["receipt_id"]),
        unsigned,
    )


def _default_systemctl(action: str) -> None:
    if action != "restart":
        raise EffectError("systemctl action is not allowlisted")
    try:
        subprocess.run(
            ["/usr/bin/systemctl", "--user", "restart", EXACT_UNIT_NAME],
            check=True,
            timeout=20,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EffectError("exact systemd restart failed") from exc


def _default_snapshot() -> ProcessSnapshot:
    try:
        completed = subprocess.run(
            [
                "/usr/bin/systemctl",
                "--user",
                "show",
                EXACT_UNIT_NAME,
                "--property=ActiveState",
                "--property=SubState",
                "--property=MainPID",
                "--property=ExecMainStartTimestampMonotonic",
                "--no-pager",
            ],
            check=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EffectError("exact systemd snapshot failed") from exc
    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key] = value
    try:
        pid = int(fields["MainPID"])
        started = int(fields["ExecMainStartTimestampMonotonic"])
        payload = {
            "unit_name": EXACT_UNIT_NAME,
            "active_state": fields["ActiveState"],
            "sub_state": fields["SubState"],
            "main_pid": pid,
            "start_timestamp_monotonic": started,
            "process_identity": f"systemd-user:{EXACT_UNIT_NAME}:pid:{pid}:start:{started}",
            "captured_at": _timestamp(datetime.now(timezone.utc)),
        }
        return ProcessSnapshot.model_validate(payload)
    except (KeyError, ValueError, ValidationError) as exc:
        raise EffectError("exact systemd process is not active and running") from exc


def _default_canary(output_root: Path, phase: str) -> tuple[CanaryReceipt, Path]:
    credential_root = os.environ.get("CREDENTIALS_DIRECTORY", "").strip()
    if not credential_root:
        raise EffectError("managed effect worker requires loaded canary credentials")
    try:
        receipt, record_path, _, _ = asyncio.run(
            run_canary(
                organ_id=EXACT_ORGAN_ID,
                secret_dir=Path(credential_root),
                output_root=output_root / phase,
                ttl_seconds=300,
                timeout_seconds=20,
            )
        )
    except Exception as exc:
        raise EffectError("authenticated postcondition canary failed") from exc
    if not receipt.call_succeeded or not receipt.result_contract_matched:
        raise EffectError("authenticated postcondition canary did not match")
    return receipt, record_path


def _validate_live_precondition(
    plan: RuntimePlanCandidate,
    observation_path: Path,
    now: datetime,
) -> tuple[Any, str]:
    observation, digest = ObservationStore(observation_path).load()
    if digest != plan.expected_observation_digest:
        raise EffectError("runtime observation drift blocks execution")
    if not (plan.created_at <= now < plan.expires_at <= observation.expires_at):
        raise EffectError("runtime plan is outside its freshness envelope")
    subject = next(
        (
            item
            for item in observation.subjects
            if item.organ_id == EXACT_ORGAN_ID and item.policy_family == EXACT_POLICY_FAMILY
        ),
        None,
    )
    if subject is None:
        raise EffectError("exact runtime subject is absent")
    if (
        not subject.process.active
        or subject.process.unit_name != EXACT_UNIT_NAME
        or subject.source.revision != plan.source_revision
        or subject.package.artifact_digest != plan.package_digest
        or subject.deploy.revision != plan.deployed_revision
        or subject.deploy.tree_digest != plan.postcondition_deploy_tree_digest
    ):
        raise EffectError("live runtime subject does not match the approved plan")
    return subject, digest


class EffectExecutor:
    def __init__(
        self,
        *,
        effect_root: Path = DEFAULT_EFFECT_ROOT,
        observation_path: Path = DEFAULT_OBSERVATION_PATH,
        systemctl_runner: SystemctlRunner = _default_systemctl,
        snapshot_runner: SnapshotRunner = _default_snapshot,
        canary_runner: CanaryRunner = _default_canary,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.root = _safe_root(effect_root)
        self.observation_path = observation_path
        self.systemctl_runner = systemctl_runner
        self.snapshot_runner = snapshot_runner
        self.canary_runner = canary_runner
        self.clock = clock

    def execute(
        self,
        *,
        plan_id: str,
        approval_id: str,
        idempotency_key: str,
    ) -> tuple[InternalEffectReceipt, bool]:
        lock_path = self.root / ".execute.lock"
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                if IDEMPOTENCY_PATTERN.fullmatch(idempotency_key) is None:
                    raise EffectError("idempotency key is invalid")
                return self._execute_locked(
                    plan_id=plan_id,
                    approval_id=approval_id,
                    idempotency_key=idempotency_key,
                )
            except EffectRecoveryError:
                raise
            except EffectError as exc:
                _write_denial_receipt(
                    self.root,
                    plan_id=plan_id,
                    approval_id=approval_id,
                    idempotency_key=idempotency_key,
                    error=exc,
                    observed_at=_utc(self.clock()),
                )
                raise
        finally:
            os.close(descriptor)

    def _execute_locked(
        self,
        *,
        plan_id: str,
        approval_id: str,
        idempotency_key: str,
    ) -> tuple[InternalEffectReceipt, bool]:
        replay_path = self.root / "idempotency" / f"{hashlib.sha256(idempotency_key.encode()).hexdigest()}.json"
        if replay_path.exists():
            replay = _read_private(replay_path, "idempotency receipt")
            try:
                receipt = InternalEffectReceipt.model_validate(replay["receipt"])
            except (KeyError, ValidationError) as exc:
                raise EffectError("idempotency receipt is invalid") from exc
            if receipt.plan_id != plan_id or receipt.approval_id != approval_id:
                raise EffectError("idempotency key is already bound to another request")
            return receipt, True

        plan = _load_plan(self.root, plan_id)
        approval = _load_approval(self.root, approval_id)
        _validate_exact_plan_shape(plan)
        now = _utc(self.clock())
        if (
            approval.plan_id != plan.plan_id
            or approval.idempotency_key != idempotency_key
            or not (approval.issued_at <= now < approval.expires_at <= plan.expires_at)
        ):
            raise EffectError("approval does not authorize this exact live request")
        subject, observation_digest = _validate_live_precondition(
            plan, self.observation_path, now
        )
        _claim_rate_slot(
            self.root,
            plan_id=plan.plan_id,
            approval_id=approval.approval_id,
            idempotency_key=idempotency_key,
            observed_at=now,
        )
        pre_effect = self.snapshot_runner()
        if pre_effect.process_identity != subject.process.process_identity:
            raise EffectError("systemd precondition drift blocks execution")

        preflight = {
            "schema_version": "abyss_stack_internal_effect_preflight_v1",
            "plan_id": plan.plan_id,
            "approval_id": approval.approval_id,
            "idempotency_key": idempotency_key,
            "exact_unit_name": EXACT_UNIT_NAME,
            "expected_observation_digest": observation_digest,
            "pre_effect": pre_effect.model_dump(mode="json"),
            "approval_verified": True,
            "source_to_sink_policy_verified": True,
            "runtime_effect_authorized": True,
            "observed_at": _timestamp(now),
            "contains_secrets": False,
        }
        _write_private(
            self.root / "pre-effects" / f"{plan.plan_id.removeprefix('sha256:')}.{hashlib.sha256(idempotency_key.encode()).hexdigest()}.json",
            preflight,
        )

        post_errors: list[BaseException] = []
        post_effect: ProcessSnapshot | None = None
        post_canary_path: Path | None = None
        post_rollback: ProcessSnapshot | None = None
        rollback_canary_path: Path | None = None
        rollback_succeeded = False
        try:
            try:
                self.systemctl_runner("restart")
                post_effect = self.snapshot_runner()
                if post_effect.process_identity == pre_effect.process_identity:
                    raise EffectError(
                        "restart did not produce a new exact process identity"
                    )
                _, post_canary_path = self.canary_runner(
                    self.root
                    / "canaries"
                    / hashlib.sha256(idempotency_key.encode()).hexdigest(),
                    "post-effect",
                )
            except Exception as exc:  # rollback is mandatory after any attempt
                post_errors.append(exc)
        finally:
            try:
                self.systemctl_runner("restart")
                post_rollback = self.snapshot_runner()
                if post_rollback.process_identity == pre_effect.process_identity or (
                    post_effect is not None
                    and post_rollback.process_identity == post_effect.process_identity
                ):
                    raise EffectError(
                        "rollback restart did not produce a new process identity"
                    )
                _, rollback_canary_path = self.canary_runner(
                    self.root
                    / "canaries"
                    / hashlib.sha256(idempotency_key.encode()).hexdigest(),
                    "post-rollback",
                )
                rollback_succeeded = True
            except Exception as exc:
                post_errors.append(exc)

        if (
            post_errors
            or post_effect is None
            or post_canary_path is None
            or not rollback_succeeded
            or post_rollback is None
            or rollback_canary_path is None
        ):
            _write_recovery_receipt(
                self.root,
                plan=plan,
                approval=approval,
                idempotency_key=idempotency_key,
                post_effect=post_effect,
                post_effect_canary_path=post_canary_path,
                rollback_succeeded=rollback_succeeded,
                post_rollback=post_rollback,
                post_rollback_canary_path=rollback_canary_path,
                reason_codes=tuple(_reason_code(error) for error in post_errors)
                or ("postcondition_incomplete",),
                observed_at=_utc(self.clock()),
            )
            if rollback_succeeded:
                raise EffectRecoveryError(
                    "post-effect verification failed after successful automatic rollback"
                )
            raise EffectRecoveryError(
                "internal-effect attempt failed and automatic rollback was not proved"
            )
        observed_at = _utc(self.clock())
        unsigned = {
            "schema_version": "abyss_stack_internal_effect_receipt_v1",
            "issuer": "abyss-stack",
            "tool_id": EXACT_TOOL_ID,
            "plan_id": plan.plan_id,
            "approval_id": approval.approval_id,
            "idempotency_key": idempotency_key,
            "target_organ_id": EXACT_ORGAN_ID,
            "target_policy_family": EXACT_POLICY_FAMILY,
            "exact_unit_name": EXACT_UNIT_NAME,
            "expected_observation_digest": observation_digest,
            "source_revision": plan.source_revision,
            "package_digest": plan.package_digest,
            "deployed_revision": plan.deployed_revision,
            "deployed_tree_digest": plan.postcondition_deploy_tree_digest,
            "pre_effect": pre_effect.model_dump(mode="json"),
            "post_effect": post_effect.model_dump(mode="json"),
            "post_effect_canary_ref": post_canary_path.as_posix(),
            "post_effect_canary_digest": _digest_bytes(post_canary_path.read_bytes()),
            "post_effect_canary_succeeded": True,
            "rollback_target_process_identity": pre_effect.process_identity,
            "rollback_executed": True,
            "post_rollback": post_rollback.model_dump(mode="json"),
            "post_rollback_canary_ref": rollback_canary_path.as_posix(),
            "post_rollback_canary_digest": _digest_bytes(rollback_canary_path.read_bytes()),
            "post_rollback_canary_succeeded": True,
            "outcome": "succeeded_rolled_back",
            "actual_effects": ["restart_exact_unit", "rollback_restart_exact_unit"],
            "approval_verified": True,
            "source_to_sink_policy_verified": True,
            "runtime_effect_authorized": True,
            "external_effect_authorized": False,
            "observed_at": _timestamp(observed_at),
            "contains_secrets": False,
            "claim_limit": (
                "This receipt proves one approved restart and one executed rollback restart "
                "of abyss-stack-mcp-read.service with authenticated post-effect and "
                "post-rollback canaries. It authorizes no other unit, command, source "
                "mutation, credential use, admission, or external effect."
            ),
        }
        receipt = InternalEffectReceipt.model_validate({"receipt_id": _digest(unsigned), **unsigned})
        receipt_path = _artifact_path(self.root, "receipts", receipt.receipt_id)
        _write_private(receipt_path, receipt.model_dump(mode="json"))
        _write_private(
            replay_path,
            {
                "schema_version": "abyss_stack_internal_effect_idempotency_v1",
                "receipt_id": receipt.receipt_id,
                "receipt_ref": receipt_path.as_posix(),
                "receipt": receipt.model_dump(mode="json"),
                "contains_secrets": False,
            },
        )
        return receipt, False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--effect-root", type=Path, default=DEFAULT_EFFECT_ROOT)
    parser.add_argument("--observation-path", type=Path, default=DEFAULT_OBSERVATION_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage-plan")
    stage.add_argument("--input", type=Path, required=True)
    approve = sub.add_parser("approve")
    approve.add_argument("--plan-id", required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--idempotency-key", required=True)
    approve.add_argument("--expires-at", required=True)
    execute = sub.add_parser("execute")
    execute.add_argument("--plan-id", required=True)
    execute.add_argument("--approval-id", required=True)
    execute.add_argument("--idempotency-key", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "stage-plan":
            path = stage_plan(args.input, args.effect_root)
            result = {"staged_plan_ref": path.as_posix(), "contains_secrets": False}
        elif args.command == "approve":
            expires_at = datetime.fromisoformat(args.expires_at.replace("Z", "+00:00"))
            approval, path = create_approval(
                plan_id=args.plan_id,
                approved_by=args.approved_by,
                idempotency_key=args.idempotency_key,
                expires_at=expires_at,
                effect_root=args.effect_root,
            )
            result = {
                "approval_id": approval.approval_id,
                "approval_ref": path.as_posix(),
                "contains_secrets": False,
            }
        else:
            receipt, replay = EffectExecutor(
                effect_root=args.effect_root,
                observation_path=args.observation_path,
            ).execute(
                plan_id=args.plan_id,
                approval_id=args.approval_id,
                idempotency_key=args.idempotency_key,
            )
            result = {
                "receipt": receipt.model_dump(mode="json"),
                "idempotent_replay": replay,
                "contains_secrets": False,
            }
    except (EffectError, ValidationError, ValueError) as exc:
        print(f"abyss-stack internal-effect: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
