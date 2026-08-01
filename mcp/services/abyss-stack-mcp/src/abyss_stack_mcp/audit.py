"""Tamper-evident, secret-free policy receipt journal."""

from __future__ import annotations

import argparse
import json
import os
import stat
import threading
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .core import (
    StackMCPError,
    _reject_secret_material,
    canonical_json_bytes,
    sha256_digest,
)


AUDIT_RECORD_SCHEMA = "abyss_stack_mcp_policy_audit_record_v1"
AUDIT_SUMMARY_SCHEMA = "abyss_stack_mcp_policy_audit_summary_v1"
POLICY_RECEIPT_SCHEMA = "abyss_stack_mcp_policy_receipt_v1"
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
MIN_MAX_BYTES = 64 * 1024
MAX_MAX_BYTES = 1024 * 1024 * 1024
MAX_RECORD_BYTES = 16 * 1024
PolicyFamily = Literal["read", "candidate"]
EXPECTED_RECEIPT_KEYS = {
    "schema_version",
    "request_id",
    "owner",
    "identity_id",
    "auth_mode",
    "scope",
    "policy_family",
    "tool_id",
    "effect_class",
    "decision",
    "reason_codes",
    "input_digest",
    "output_digest",
    "observed_at",
    "filesystem_access",
    "network_access",
    "source_to_sink",
    "runtime_effect_authorized",
    "approval_state",
    "content_trust",
    "instruction_authority",
    "contains_secrets",
    "receipt_id",
}
SHA256_DIGEST_PREFIX = "sha256:"
SHA256_HEX_LENGTH = 64


class PolicyAuditError(StackMCPError):
    """Fail closed without exposing journal paths or receipt values."""


def _timestamp(value: datetime) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise PolicyAuditError("policy audit clock returned an invalid timestamp")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise PolicyAuditError("policy audit timestamp is invalid")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PolicyAuditError("policy audit timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PolicyAuditError("policy audit timestamp is invalid")
    return parsed.astimezone(timezone.utc)


def _safe_absolute_path(path: Path) -> Path:
    if not path.is_absolute():
        raise PolicyAuditError("policy audit journal path must be absolute")
    absolute = path.absolute()
    for component in (*reversed(absolute.parents), absolute):
        if component.is_symlink():
            raise PolicyAuditError(
                "policy audit journal cannot traverse a symlink"
            )
    parent = absolute.parent
    if not parent.is_dir():
        raise PolicyAuditError(
            "policy audit journal parent must already exist"
        )
    if absolute.exists() and not absolute.is_file():
        raise PolicyAuditError(
            "policy audit journal must be a regular file"
        )
    return absolute


def _read_all(descriptor: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise PolicyAuditError("policy audit journal exceeds its byte limit")


def _validate_max_bytes(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolicyAuditError("policy audit max bytes must be an integer")
    if not MIN_MAX_BYTES <= value <= MAX_MAX_BYTES:
        raise PolicyAuditError(
            "policy audit max bytes is outside the supported range"
        )
    return value


def _is_bounded_text(
    value: object,
    *,
    maximum: int = 256,
) -> bool:
    return isinstance(value, str) and 0 < len(value) <= maximum


def _is_sha256_digest(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if not value.startswith(SHA256_DIGEST_PREFIX):
        return False
    suffix = value.removeprefix(SHA256_DIGEST_PREFIX)
    return (
        len(suffix) == SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in suffix)
    )


def _validate_policy_receipt(
    receipt: object,
    *,
    owner: str,
    policy_family: PolicyFamily,
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise PolicyAuditError("policy audit receipt must be an object")
    if set(receipt) != EXPECTED_RECEIPT_KEYS:
        raise PolicyAuditError("policy audit receipt fields are invalid")
    if (
        receipt.get("schema_version") != POLICY_RECEIPT_SCHEMA
        or receipt.get("owner") != owner
        or receipt.get("policy_family") != policy_family
        or receipt.get("contains_secrets") is not False
        or receipt.get("runtime_effect_authorized") is not False
        or receipt.get("content_trust") != "untrusted_data"
        or receipt.get("instruction_authority") != "none"
    ):
        raise PolicyAuditError(
            "policy audit receipt does not match the journal contour"
        )
    reason_codes = receipt.get("reason_codes")
    output_digest = receipt.get("output_digest")
    if (
        not _is_bounded_text(receipt.get("request_id"), maximum=128)
        or not _is_bounded_text(receipt.get("identity_id"))
        or receipt.get("auth_mode") not in {"bearer", "os_process"}
        or not _is_bounded_text(receipt.get("scope"))
        or not _is_bounded_text(receipt.get("tool_id"), maximum=128)
        or receipt.get("effect_class")
        not in {"observe", "prepare_candidate", "unknown"}
        or receipt.get("decision") not in {"allowed", "denied", "cancelled"}
        or not isinstance(reason_codes, list)
        or len(reason_codes) > 8
        or any(
            not _is_bounded_text(reason, maximum=128)
            for reason in reason_codes
        )
        or not _is_sha256_digest(receipt.get("input_digest"))
        or (
            output_digest is not None
            and not _is_sha256_digest(output_digest)
        )
        or receipt.get("filesystem_access")
        not in {
            "configured_observation_read",
            "configured_observation_and_orchestration_record_read",
            "none",
        }
        or receipt.get("network_access") != "none"
        or receipt.get("source_to_sink")
        not in {
            "runtime_observation_to_typed_result",
            "runtime_observation_to_nonexecuting_candidate",
            "sdk_validated_runtime_record_to_bounded_inspection",
            "none",
        }
        or receipt.get("approval_state")
        not in {"not_applicable", "required_before_runtime_effect"}
    ):
        raise PolicyAuditError("policy audit receipt values are invalid")
    _parse_timestamp(receipt.get("observed_at"))
    decision = receipt["decision"]
    if (
        (decision == "allowed" and reason_codes)
        or (decision != "allowed" and len(reason_codes) != 1)
        or (decision == "allowed" and output_digest is None)
        or (decision != "allowed" and output_digest is not None)
    ):
        raise PolicyAuditError("policy audit decision shape is invalid")
    receipt_id = receipt.get("receipt_id")
    unsigned = {
        key: value for key, value in receipt.items() if key != "receipt_id"
    }
    if (
        not isinstance(receipt_id, str)
        or receipt_id != sha256_digest(unsigned)
    ):
        raise PolicyAuditError("policy audit receipt digest is invalid")
    try:
        _reject_secret_material(receipt)
    except StackMCPError as exc:
        raise PolicyAuditError(
            "policy audit receipt contains forbidden material"
        ) from exc
    return dict(receipt)


class PolicyAuditJournal:
    """Append and validate one bounded chain for one process contour."""

    def __init__(
        self,
        path: str | Path,
        *,
        owner: str,
        policy_family: PolicyFamily,
        max_bytes: int = DEFAULT_MAX_BYTES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = _safe_absolute_path(Path(path))
        self.owner = owner
        self.policy_family = policy_family
        self.max_bytes = _validate_max_bytes(max_bytes)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._last_record_id: str | None = None
        self._sequence = 0
        self._first_recorded_at: str | None = None
        self._last_recorded_at: str | None = None
        self._byte_count = 0
        self._device: int | None = None
        self._inode: int | None = None
        self._decision_counts: Counter[str] = Counter()
        self._reason_counts: Counter[str] = Counter()
        self._tool_counts: Counter[str] = Counter()
        self._initialize_file()
        self._load()

    @property
    def journal_ref(self) -> str:
        return f"policy-audit://{self.owner}/{self.policy_family}"

    def _open(
        self,
        flags: int,
        *,
        mode: int = 0o600,
    ) -> int:
        descriptor = os.open(
            self.path,
            flags
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            raise PolicyAuditError(
                "policy audit journal must be a regular file"
            )
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            os.close(descriptor)
            raise PolicyAuditError(
                "policy audit journal permissions are too broad"
            )
        return descriptor

    def _initialize_file(self) -> None:
        try:
            descriptor = self._open(
                os.O_WRONLY | os.O_APPEND | os.O_CREAT,
            )
        except OSError as exc:
            raise PolicyAuditError(
                "policy audit journal cannot be opened"
            ) from exc
        else:
            os.close(descriptor)

    def _load(self) -> None:
        try:
            descriptor = self._open(os.O_RDONLY)
            try:
                metadata = os.fstat(descriptor)
                content = _read_all(descriptor, self.max_bytes)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise PolicyAuditError(
                "policy audit journal cannot be read"
            ) from exc
        if content and not content.endswith(b"\n"):
            raise PolicyAuditError("policy audit journal has a partial record")
        self._device = metadata.st_dev
        self._inode = metadata.st_ino
        self._byte_count = len(content)
        previous: str | None = None
        for expected_sequence, line in enumerate(
            content.splitlines(),
            start=1,
        ):
            if not line or len(line) > MAX_RECORD_BYTES:
                raise PolicyAuditError("policy audit record size is invalid")
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise PolicyAuditError(
                    "policy audit record is invalid JSON"
                ) from exc
            self._validate_record(
                record,
                expected_sequence=expected_sequence,
                expected_previous=previous,
            )
            previous = record["record_id"]
            self._observe_record(record)

    def _validate_record(
        self,
        record: object,
        *,
        expected_sequence: int,
        expected_previous: str | None,
    ) -> None:
        if not isinstance(record, dict):
            raise PolicyAuditError("policy audit record must be an object")
        expected_keys = {
            "schema_version",
            "journal_ref",
            "sequence",
            "previous_record_id",
            "recorded_at",
            "policy_receipt",
            "record_id",
        }
        if set(record) != expected_keys:
            raise PolicyAuditError("policy audit record fields are invalid")
        if (
            record.get("schema_version") != AUDIT_RECORD_SCHEMA
            or record.get("journal_ref") != self.journal_ref
            or type(record.get("sequence")) is not int
            or record.get("sequence") != expected_sequence
            or record.get("previous_record_id") != expected_previous
        ):
            raise PolicyAuditError("policy audit continuity is invalid")
        recorded_at = _parse_timestamp(record.get("recorded_at"))
        validated_receipt = _validate_policy_receipt(
            record.get("policy_receipt"),
            owner=self.owner,
            policy_family=self.policy_family,
        )
        receipt_observed_at = _parse_timestamp(
            validated_receipt.get("observed_at")
        )
        if receipt_observed_at > recorded_at:
            raise PolicyAuditError(
                "policy audit record predates its policy receipt"
            )
        if (
            self._last_recorded_at is not None
            and recorded_at < _parse_timestamp(self._last_recorded_at)
        ):
            raise PolicyAuditError(
                "policy audit record timestamps are not monotonic"
            )
        record_id = record.get("record_id")
        unsigned = {
            key: value for key, value in record.items() if key != "record_id"
        }
        if (
            not isinstance(record_id, str)
            or record_id != sha256_digest(unsigned)
        ):
            raise PolicyAuditError("policy audit record digest is invalid")

    def _observe_record(self, record: dict[str, Any]) -> None:
        receipt = record["policy_receipt"]
        self._sequence = record["sequence"]
        self._last_record_id = record["record_id"]
        recorded_at = record["recorded_at"]
        if self._first_recorded_at is None:
            self._first_recorded_at = recorded_at
        self._last_recorded_at = recorded_at
        self._decision_counts[str(receipt["decision"])] += 1
        self._tool_counts[str(receipt["tool_id"])] += 1
        for reason in receipt["reason_codes"]:
            self._reason_counts[str(reason)] += 1

    def append(self, receipt: dict[str, Any]) -> str:
        validated = _validate_policy_receipt(
            receipt,
            owner=self.owner,
            policy_family=self.policy_family,
        )
        with self._lock:
            body = {
                "schema_version": AUDIT_RECORD_SCHEMA,
                "journal_ref": self.journal_ref,
                "sequence": self._sequence + 1,
                "previous_record_id": self._last_record_id,
                "recorded_at": _timestamp(self._clock()),
                "policy_receipt": validated,
            }
            record = {
                **body,
                "record_id": sha256_digest(body),
            }
            self._validate_record(
                record,
                expected_sequence=self._sequence + 1,
                expected_previous=self._last_record_id,
            )
            rendered = canonical_json_bytes(record) + b"\n"
            if len(rendered) > MAX_RECORD_BYTES:
                raise PolicyAuditError("policy audit record exceeds its byte limit")
            try:
                descriptor = self._open(os.O_WRONLY | os.O_APPEND)
                try:
                    metadata = os.fstat(descriptor)
                    if (
                        metadata.st_dev != self._device
                        or metadata.st_ino != self._inode
                    ):
                        raise PolicyAuditError(
                            "policy audit journal identity changed"
                        )
                    current_size = metadata.st_size
                    if current_size != self._byte_count:
                        raise PolicyAuditError(
                            "policy audit journal changed outside this process"
                        )
                    if current_size + len(rendered) > self.max_bytes:
                        raise PolicyAuditError(
                            "policy audit journal capacity is exhausted"
                        )
                    offset = 0
                    while offset < len(rendered):
                        written = os.write(descriptor, rendered[offset:])
                        if written <= 0:
                            raise OSError("short policy audit write")
                        offset += written
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except PolicyAuditError:
                raise
            except OSError as exc:
                raise PolicyAuditError(
                    "policy audit journal write failed"
                ) from exc
            self._observe_record(record)
            self._byte_count += len(rendered)
            return record["record_id"]

    def summary(self) -> dict[str, Any]:
        with self._lock:
            try:
                descriptor = self._open(os.O_RDONLY)
                try:
                    metadata = os.fstat(descriptor)
                    if (
                        metadata.st_dev != self._device
                        or metadata.st_ino != self._inode
                    ):
                        raise PolicyAuditError(
                            "policy audit journal identity changed"
                        )
                    byte_count = metadata.st_size
                finally:
                    os.close(descriptor)
            except PolicyAuditError:
                raise
            except OSError as exc:
                raise PolicyAuditError(
                    "policy audit journal cannot be observed"
                ) from exc
            if byte_count != self._byte_count:
                raise PolicyAuditError(
                    "policy audit journal changed outside this process"
                )
            return {
                "schema_version": AUDIT_SUMMARY_SCHEMA,
                "owner": self.owner,
                "policy_family": self.policy_family,
                "journal_ref": self.journal_ref,
                "continuity_state": "exact",
                "records": self._sequence,
                "byte_count": byte_count,
                "max_bytes": self.max_bytes,
                "remaining_bytes": self.max_bytes - byte_count,
                "first_recorded_at": self._first_recorded_at,
                "last_recorded_at": self._last_recorded_at,
                "latest_record_id": self._last_record_id,
                "decision_counts": dict(sorted(self._decision_counts.items())),
                "reason_counts": dict(sorted(self._reason_counts.items())),
                "tool_counts": dict(sorted(self._tool_counts.items())),
                "contains_secrets": False,
                "claim_limit": (
                    "This summary proves local journal shape and hash-chain "
                    "continuity only. It does not prove caller intent, result "
                    "grounding, owner acceptance, admission, or runtime effects."
                ),
            }


def main() -> None:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-audit")
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--owner", default="abyss-stack")
    parser.add_argument(
        "--policy-family",
        choices=("read", "candidate"),
        required=True,
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
    )
    args = parser.parse_args()
    journal = PolicyAuditJournal(
        args.journal,
        owner=args.owner,
        policy_family=args.policy_family,
        max_bytes=args.max_bytes,
    )
    print(
        json.dumps(
            journal.summary(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
