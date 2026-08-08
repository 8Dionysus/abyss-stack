#!/usr/bin/env python3
"""Durable runtime-owner controller for one external Codex incarnation.

The controller launches Codex as a distinct operating-system process. It never
uses Codex's built-in subagent transport. Exact aoa-sdk plan and incarnation
objects are validated before launch; runtime state and normalized events stay
under an explicit state root.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import selectors
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker

from aoa_sdk.contracts.control_plane import ProvenanceRef, RunPlan
from aoa_sdk.contracts.incarnation import AgentIncarnationBinding
from aoa_sdk.control_plane.incarnation import (
    assert_agent_incarnation_binding_matches_plan,
)


PART_ROOT = Path(__file__).resolve().parent
PROFILE_PATH = PART_ROOT / "runtime-profile.v1.json"
SUPERVISOR_PATH = PART_ROOT / "external_codex_supervisor.py"
SCHEMA_ROOT = PART_ROOT / "schemas"
LAUNCH_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-launch.schema.json"
TASK_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-task.schema.json"
PROFILE_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-runtime-profile.schema.json"
REPORT_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-report.schema.json"
EVENT_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-event.schema.json"
RESULT_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-result.schema.json"
RESUME_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-resume.schema.json"
STATE_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-state.schema.json"
PARENT_OBLIGATION_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-parent-obligation.schema.json"
)
PARENT_YIELD_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-parent-yield.schema.json"
PARENT_REENTRY_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-parent-reentry.schema.json"
)
REENTRY_STATE_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-reentry-state.schema.json"
WORKSPACE_MANIFEST_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-workspace-manifest.schema.json"
)
SDK_SUMMON_REQUEST_SCHEMA_REF = (
    "mechanics/checkpoint/parts/child-task-reentry/schemas/"
    "summon-request-v4.schema.json"
)
SDK_SUMMON_REQUEST_SCHEMA_VERSION = "urn:aoa-sdk:a2a:summon-request:v4"

LEGACY_STATE_SCHEMA_VERSION = "abyss_stack_external_codex_runtime_state_v1"
STATE_SCHEMA_VERSION = "abyss_stack_external_codex_runtime_state_v2"
RESPONSE_SCHEMA_VERSION = "abyss_stack_external_codex_response_v1"
REENTRY_STATE_SCHEMA_VERSION = "abyss_stack_external_codex_reentry_state_v1"
MAX_CONTROL_BYTES = 16 * 1024 * 1024
MAX_ROLE_BYTES = 2 * 1024 * 1024
MAX_EVENT_LINE_BYTES = 8 * 1024 * 1024
FOREGROUND_OBSERVATION_INTERVAL_SECONDS = 0.25
TERMINAL_STATES = {
    "completed",
    "failed",
    "paused",
    "review_required",
    "authority_blocked",
}
RESUMABLE_STATES = {"paused", "interrupted", "review_required"}
REVIEW_REPORT_RECOVERY_FAILURES = {"model_report_identity_mismatch"}
SECRET_ENV_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)
SOURCE_LINE_ANCHOR_RE = re.compile(r"^L(?P<start>[1-9][0-9]*)(?:-L(?P<end>[1-9][0-9]*))?$")
INPUT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHELL_NAMES = {"bash", "dash", "sh", "zsh"}
SHELL_SEPARATORS = {"&", "&&", ";", "|", "||"}
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", re.S)
SECRET_PATH_PARTS = {
    ".aws",
    ".gnupg",
    ".ssh",
    "credential",
    "credentials",
    "secret",
    "secrets",
}


def _plan_binds_active_summon_request(
    plan: RunPlan, request_ref: ProvenanceRef
) -> bool:
    """Accept the typed A2A slot or the exact domain-scenario input slot."""

    typed = [
        item.artifact_ref
        for item in plan.scenario_binding.input_artifact_bindings
        if item.artifact_kind == "summon_request"
    ]
    if typed:
        return typed == [request_ref]
    generic = [item for item in plan.scenario_binding.input_refs if item == request_ref]
    return generic == [request_ref]
SECRET_FILE_NAMES = {
    ".env",
    ".netrc",
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
READ_CAPABLE_COMMANDS = {
    "awk",
    "cat",
    "cp",
    "cut",
    "dd",
    "find",
    "grep",
    "head",
    "jq",
    "less",
    "more",
    "perl",
    "python",
    "python3",
    "rg",
    "ruby",
    "sed",
    "strings",
    "tail",
    "tar",
    "tee",
}
OPAQUE_EFFECT_EXECUTABLES = {
    "deno",
    "lua",
    "node",
    "perl",
    "php",
    "python",
    "python3",
    "ruby",
}
SYSTEM_PATH_PREFIXES = ("/etc", "/opt", "/usr", "/var/lib", "/var/run")


class ExternalCodexRuntimeError(RuntimeError):
    """One fail-closed external-agent runtime error with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "artifact_unavailable", f"cannot hash runtime coordinate: {path}"
        ) from exc
    return "sha256:" + digest.hexdigest()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)


def read_bounded(path: Path, *, limit: int = MAX_CONTROL_BYTES) -> bytes:
    if not path.is_absolute():
        raise ExternalCodexRuntimeError(
            "path_not_absolute", f"runtime coordinate is not absolute: {path}"
        )
    try:
        with path.open("rb") as handle:
            payload = handle.read(limit + 1)
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "artifact_unavailable", f"cannot read runtime coordinate: {path}"
        ) from exc
    if len(payload) > limit:
        raise ExternalCodexRuntimeError(
            "artifact_too_large", f"runtime coordinate exceeds {limit} bytes: {path}"
        )
    return payload


def load_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalCodexRuntimeError(
            "invalid_json", f"{label} is not valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise ExternalCodexRuntimeError(
            "invalid_json", f"{label} must be a JSON object"
        )
    return value


def load_json(path: Path, *, label: str) -> dict[str, Any]:
    return load_json_bytes(read_bounded(path), label=label)


def load_schema(path: Path) -> dict[str, Any]:
    schema = load_json(path, label=f"schema {path.name}")
    Draft202012Validator.check_schema(schema)
    return schema


def validate_json(value: Any, schema_path: Path, *, label: str) -> None:
    validator = Draft202012Validator(
        load_schema(schema_path),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = "/".join(str(item) for item in first.path) or "<root>"
        raise ExternalCodexRuntimeError(
            "schema_validation_failed",
            f"{label} violates {schema_path.name} at {location}: {first.message}",
        )


def validate_structured_output_schema(schema: Mapping[str, Any]) -> None:
    """Fail before inference when a schema exceeds OpenAI Structured Outputs."""

    unsupported = {
        "allOf",
        "not",
        "dependentRequired",
        "dependentSchemas",
        "if",
        "then",
        "else",
        "uniqueItems",
    }

    def walk(node: Mapping[str, Any], path: str) -> None:
        found = unsupported.intersection(node)
        if found:
            raise ExternalCodexRuntimeError(
                "codex_output_schema_unsupported",
                f"output schema uses unsupported keywords at {path}: {sorted(found)}",
            )
        properties = node.get("properties")
        if properties is not None:
            if node.get("type") != "object" or not isinstance(properties, dict):
                raise ExternalCodexRuntimeError(
                    "codex_output_schema_unsupported",
                    f"output schema properties lack an object type at {path}",
                )
            if node.get("additionalProperties") is not False:
                raise ExternalCodexRuntimeError(
                    "codex_output_schema_unsupported",
                    f"output schema object must close additional properties at {path}",
                )
            required = node.get("required")
            if not isinstance(required, list) or set(required) != set(properties):
                raise ExternalCodexRuntimeError(
                    "codex_output_schema_unsupported",
                    f"every output schema property must be required at {path}",
                )
            for name, child in properties.items():
                if not isinstance(child, dict):
                    raise ExternalCodexRuntimeError(
                        "codex_output_schema_unsupported",
                        f"output schema property is not an object at {path}/{name}",
                    )
                if not any(key in child for key in ("type", "$ref", "anyOf")):
                    raise ExternalCodexRuntimeError(
                        "codex_output_schema_unsupported",
                        f"output schema property lacks a type at {path}/{name}",
                    )
                walk(child, f"{path}/{name}")
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, f"{path}/items")
        choices = node.get("anyOf")
        if isinstance(choices, list):
            for index, child in enumerate(choices):
                if not isinstance(child, dict):
                    raise ExternalCodexRuntimeError(
                        "codex_output_schema_unsupported",
                        f"output schema anyOf entry is invalid at {path}/{index}",
                    )
                walk(child, f"{path}/anyOf/{index}")
        definitions = node.get("$defs")
        if isinstance(definitions, dict):
            for name, child in definitions.items():
                if isinstance(child, dict):
                    walk(child, f"{path}/$defs/{name}")

    if schema.get("type") != "object" or "anyOf" in schema:
        raise ExternalCodexRuntimeError(
            "codex_output_schema_unsupported",
            "output schema root must be one object and cannot be anyOf",
        )
    walk(schema, "<root>")


def specialize_report_schema(
    schema: Mapping[str, Any],
    *,
    task_id: str,
    incarnation_id: str,
    immutable_input_ids: Sequence[str],
) -> dict[str, Any]:
    """Bind one canonical report schema to exact runtime/evidence identities."""

    specialized = json.loads(json.dumps(schema))
    properties = specialized.get("properties")
    if not isinstance(properties, dict):
        raise ExternalCodexRuntimeError(
            "runtime_profile_invalid",
            "canonical report schema has no properties object",
        )
    for field, expected in (
        ("task_id", task_id),
        ("incarnation_id", incarnation_id),
    ):
        field_schema = properties.get(field)
        if not isinstance(field_schema, dict) or field_schema.get("type") != "string":
            raise ExternalCodexRuntimeError(
                "runtime_profile_invalid",
                f"canonical report schema cannot bind {field}",
            )
        field_schema["const"] = expected
    exact_input_ids = tuple(sorted({str(value) for value in immutable_input_ids}))
    if not exact_input_ids or any(
        INPUT_ID_RE.fullmatch(value) is None for value in exact_input_ids
    ):
        raise ExternalCodexRuntimeError(
            "runtime_profile_invalid",
            "session-local report schema requires valid immutable input identities",
        )
    immutable_alternation = "|".join(re.escape(value) for value in exact_input_ids)
    evidence_pattern = (
        "^(?:source:[^#]+|immutable:(?:"
        f"{immutable_alternation}"
        ")|runtime:workspace-final-manifest)#[^#]+$"
    )
    findings = properties.get("findings")
    transition = properties.get("transition")
    finding_items = findings.get("items") if isinstance(findings, dict) else None
    finding_properties = (
        finding_items.get("properties")
        if isinstance(finding_items, dict)
        else None
    )
    transition_properties = (
        transition.get("properties") if isinstance(transition, dict) else None
    )
    evidence_arrays = (
        (
            "findings",
            finding_properties.get("evidence_refs")
            if isinstance(finding_properties, dict)
            else None,
        ),
        (
            "transition",
            transition_properties.get("evidence_refs")
            if isinstance(transition_properties, dict)
            else None,
        ),
    )
    for label, evidence_array in evidence_arrays:
        if (
            not isinstance(evidence_array, dict)
            or not isinstance(evidence_array.get("items"), dict)
            or evidence_array["items"].get("type") != "string"
        ):
            raise ExternalCodexRuntimeError(
                "runtime_profile_invalid",
                f"canonical report schema cannot bind {label} evidence identities",
            )
        evidence_array["items"]["pattern"] = evidence_pattern
    Draft202012Validator.check_schema(specialized)
    validate_structured_output_schema(specialized)
    return specialized


def _atomic_write_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    payload = (
        json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(path, payload, mode=mode)


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_EVENT_LINE_BYTES:
        raise ExternalCodexRuntimeError(
            "runtime_event_record_too_large",
            "one normalized event exceeds the per-record safety boundary",
        )
    with path.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _iter_jsonl_bytes(
    path: Path,
    *,
    failure_code: str,
    label: str,
) -> Iterator[tuple[int, bytes]]:
    """Stream newline-delimited records with a per-record, not aggregate, cap."""

    with path.open("rb") as handle:
        line_number = 0
        while True:
            line = handle.readline(MAX_EVENT_LINE_BYTES + 1)
            if not line:
                return
            line_number += 1
            if len(line) > MAX_EVENT_LINE_BYTES:
                raise ExternalCodexRuntimeError(
                    failure_code,
                    f"{label} line {line_number} exceeds the per-record safety boundary",
                )
            if not line.endswith(b"\n"):
                raise ExternalCodexRuntimeError(
                    failure_code,
                    f"{label} ends with a partial record at line {line_number}",
                )
            yield line_number, line


def _artifact_ref(path: Path, *, owner: str = "abyss-stack") -> dict[str, str]:
    return {
        "owner_repo": owner,
        "artifact_ref": str(path),
        "artifact_digest": sha256_file(path),
    }


def _verified_artifact_ref_path(
    ref: Mapping[str, Any],
    *,
    label: str,
) -> Path:
    value = ref.get("artifact_ref")
    digest = ref.get("artifact_digest")
    if not isinstance(value, str) or not isinstance(digest, str):
        raise ExternalCodexRuntimeError(
            "a2a_artifact_ref_invalid",
            f"{label} has no exact artifact path and digest",
        )
    path = Path(value)
    if (
        not path.is_absolute()
        or not path.is_file()
        or path.is_symlink()
        or sha256_file(path) != digest
    ):
        raise ExternalCodexRuntimeError(
            "a2a_artifact_drift",
            f"{label} bytes differ from the terminal runtime receipt",
        )
    return path


def _load_verified_json_ref(
    ref: Mapping[str, Any],
    *,
    label: str,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    path = _verified_artifact_ref_path(ref, label=label)
    value = load_json(path, label=label)
    if schema_path is not None:
        validate_json(value, schema_path, label=label)
    return value


def _process_start_ticks(pid: int) -> int | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = raw.rfind(")")
        if close < 0:
            return None
        fields = raw[close + 2 :].split()
        if fields[0] == "Z":
            return None
        return int(fields[19])
    except (OSError, IndexError, ValueError):
        return None


def _process_group_identity(pid: int) -> tuple[str, int, int, int] | None:
    """Return state, process group, session, and start ticks from Linux procfs."""

    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = raw.rfind(")")
        if close < 0:
            return None
        fields = raw[close + 2 :].split()
        return fields[0], int(fields[2]), int(fields[3]), int(fields[19])
    except (OSError, IndexError, ValueError):
        return None


def _process_parent_identity(
    pid: int,
) -> tuple[str, int, int, int, int] | None:
    """Return state, parent, process group, session, and start ticks."""

    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = raw.rfind(")")
        if close < 0:
            return None
        fields = raw[close + 2 :].split()
        return (
            fields[0],
            int(fields[1]),
            int(fields[2]),
            int(fields[3]),
            int(fields[19]),
        )
    except (OSError, IndexError, ValueError):
        return None


def _owned_process_group_members(pgid: int, leader_start_ticks: int) -> tuple[int, ...]:
    """Identify the exact start_new_session group, including a dead leader's children."""

    if pgid <= 1 or leader_start_ticks <= 0:
        raise ExternalCodexRuntimeError(
            "codex_process_identity_invalid", "Codex process-group identity is incomplete"
        )
    leader = _process_group_identity(pgid)
    if leader is not None and leader[0] != "Z" and leader[3] != leader_start_ticks:
        raise ExternalCodexRuntimeError(
            "codex_process_identity_drift", "Codex leader PID was reused"
        )
    members: list[int] = []
    try:
        proc_entries = tuple(Path("/proc").iterdir())
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "codex_process_observation_failed", "cannot enumerate Codex process group"
        ) from exc
    for entry in proc_entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        identity = _process_group_identity(pid)
        if identity is None or identity[0] == "Z":
            continue
        _, process_group, session_id, _ = identity
        if process_group == pgid and session_id == pgid:
            members.append(pid)
    return tuple(sorted(members))


def _terminate_owned_process_group(
    pgid: int,
    leader_start_ticks: int,
    *,
    term_timeout: float = 3.0,
    kill_timeout: float = 3.0,
) -> None:
    """Terminate one exact Codex session and prove that no descendant remains."""

    members = _owned_process_group_members(pgid, leader_start_ticks)
    if not members:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + term_timeout
    while time.monotonic() < deadline:
        if not _owned_process_group_members(pgid, leader_start_ticks):
            return
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + kill_timeout
    while time.monotonic() < deadline:
        if not _owned_process_group_members(pgid, leader_start_ticks):
            return
        time.sleep(0.05)
    remaining = _owned_process_group_members(pgid, leader_start_ticks)
    if remaining:
        raise ExternalCodexRuntimeError(
            "codex_process_cleanup_incomplete",
            "Codex process group retained live members after bounded SIGKILL",
        )


def _pid_matches(pid: Any, start_ticks: Any) -> bool:
    if not isinstance(pid, int) or pid <= 1 or not isinstance(start_ticks, int):
        return False
    return _process_start_ticks(pid) == start_ticks


def _state_supervisor_identity(state: Mapping[str, Any]) -> tuple[Any, Any]:
    """Use explicit supervisor identity, with read-only v2 receipt compatibility."""

    supervisor_pid = state.get("supervisor_pid")
    supervisor_ticks = state.get("supervisor_start_ticks")
    if isinstance(supervisor_pid, int) and isinstance(supervisor_ticks, int):
        return supervisor_pid, supervisor_ticks
    return state.get("codex_pid"), state.get("codex_start_ticks")


def _wait_for_process_identity_receipt(
    path: Path,
    *,
    process: subprocess.Popen[bytes],
    supervisor_start_ticks: int,
    timeout_seconds: float = 5.0,
) -> tuple[dict[str, int | str], dict[str, str]]:
    deadline = time.monotonic() + timeout_seconds
    while not path.is_file():
        if process.poll() is not None or time.monotonic() >= deadline:
            raise ExternalCodexRuntimeError(
                "codex_process_identity_invalid",
                "supervisor did not publish the exact Codex process identity",
            )
        time.sleep(0.01)
    if path.is_symlink():
        raise ExternalCodexRuntimeError(
            "codex_process_identity_invalid",
            "process identity receipt must be a regular non-symlink file",
        )
    receipt = load_json(path, label="external Codex process identity")
    expected_keys = {
        "schema_version",
        "supervisor_pid",
        "supervisor_start_ticks",
        "codex_pid",
        "codex_start_ticks",
    }
    if set(receipt) != expected_keys or receipt.get("schema_version") != (
        "abyss_stack_external_codex_process_identity_v1"
    ):
        raise ExternalCodexRuntimeError(
            "codex_process_identity_invalid",
            "process identity receipt has an unsupported shape",
        )
    supervisor_pid = receipt.get("supervisor_pid")
    codex_pid = receipt.get("codex_pid")
    codex_start_ticks = receipt.get("codex_start_ticks")
    if (
        supervisor_pid != process.pid
        or receipt.get("supervisor_start_ticks") != supervisor_start_ticks
        or not isinstance(codex_pid, int)
        or codex_pid <= 1
        or not isinstance(codex_start_ticks, int)
        or codex_start_ticks <= 0
    ):
        raise ExternalCodexRuntimeError(
            "codex_process_identity_invalid",
            "process identity receipt differs from the launched supervisor",
        )
    current = _process_parent_identity(codex_pid)
    if current is not None and (
        current[1] != supervisor_pid
        or current[2] != supervisor_pid
        or current[3] != supervisor_pid
        or current[4] != codex_start_ticks
    ):
        raise ExternalCodexRuntimeError(
            "codex_process_identity_invalid",
            "live Codex identity differs from the supervisor receipt",
        )
    return receipt, _artifact_ref(path)


def _reap_owned_child(pid: Any, start_ticks: Any) -> None:
    if (
        not isinstance(pid, int)
        or pid <= 1
        or not isinstance(start_ticks, int)
        or start_ticks <= 0
    ):
        return
    identity = _process_group_identity(pid)
    if identity is None or identity[3] != start_ticks:
        return
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass


def _session_token(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]


def _relative_path_is_allowed(path: str, allowed: Sequence[str]) -> bool:
    def safe_parts(value: str) -> tuple[str, ...] | None:
        if (
            not value
            or value.startswith("/")
            or "\\" in value
            or "\0" in value
        ):
            return None
        parts = tuple(value.split("/"))
        if any(part in {"", ".", ".."} for part in parts):
            return None
        return parts

    path_parts = safe_parts(path)
    if path_parts is None:
        return False
    for candidate in allowed:
        candidate_parts = safe_parts(candidate)
        if candidate_parts is None:
            continue
        if path_parts[: len(candidate_parts)] == candidate_parts:
            return True
    return False


def _workspace_artifact_path(workspace: str | Path, value: str) -> Path:
    """Resolve one produced regular file without following workspace symlinks."""

    root = Path(workspace).resolve()
    candidate = root.joinpath(*value.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ExternalCodexRuntimeError(
            "model_report_artifact_unavailable",
            "model report artifact is absent or resolves outside the workspace",
        ) from exc
    if resolved != candidate or candidate.is_symlink() or not candidate.is_file():
        raise ExternalCodexRuntimeError(
            "model_report_artifact_unavailable",
            "model report artifact must be a produced regular workspace file",
        )
    return candidate


def _validate_evidence_anchor(
    raw: bytes,
    anchor: str,
    *,
    label: str,
    error_code: str,
) -> None:
    """Validate one bounded line or literal-symbol anchor against exact bytes."""

    line_match = SOURCE_LINE_ANCHOR_RE.fullmatch(anchor)
    if line_match is not None:
        start = int(line_match.group("start"))
        end = int(line_match.group("end") or start)
        line_count = len(raw.splitlines())
        if end < start or end > line_count:
            raise ExternalCodexRuntimeError(
                error_code,
                f"model report evidence line anchor is outside {label}",
            )
        return
    if len(anchor) > 256 or any(ord(character) < 32 for character in anchor):
        raise ExternalCodexRuntimeError(
            error_code,
            "model report evidence symbol anchor is invalid",
        )
    if anchor.encode("utf-8") not in raw:
        raise ExternalCodexRuntimeError(
            error_code,
            f"model report evidence symbol anchor is absent from {label}",
        )


def _validate_source_evidence_ref(
    value: str,
    workspace: str | Path,
    *,
    source_evidence_paths: Sequence[str],
) -> None:
    """Validate one anchored source reference against exact workspace bytes."""

    if not value.startswith("source:"):
        raise ExternalCodexRuntimeError(
            "model_report_evidence_scheme_unsupported",
            "model report source evidence must use the source: scheme",
        )
    body = value.removeprefix("source:")
    relative, separator, anchor = body.partition("#")
    parts = tuple(relative.split("/"))
    if (
        not relative
        or relative.startswith("/")
        or "\\" in relative
        or "\0" in relative
        or any(part in {"", ".", ".."} for part in parts)
        or not separator
        or not anchor
        or "#" in anchor
    ):
        raise ExternalCodexRuntimeError(
            "model_report_source_evidence_invalid",
            "model report source evidence has an invalid relative path or anchor",
        )
    if not _relative_path_is_allowed(relative, source_evidence_paths):
        raise ExternalCodexRuntimeError(
            "model_report_source_evidence_out_of_scope",
            "model report source evidence is outside the task source evidence paths",
        )
    if _secret_shaped_path(relative):
        raise ExternalCodexRuntimeError(
            "model_report_source_evidence_secret_shaped",
            "model report source evidence names a secret-shaped path",
        )
    root = Path(workspace).resolve()
    candidate = root.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ExternalCodexRuntimeError(
            "model_report_source_evidence_unavailable",
            f"model report source evidence is absent or outside the workspace: {relative}",
        ) from exc
    if resolved != candidate or candidate.is_symlink() or not candidate.is_file():
        raise ExternalCodexRuntimeError(
            "model_report_source_evidence_unavailable",
            f"model report source evidence is not a regular workspace file: {relative}",
        )
    try:
        raw = read_bounded(candidate)
    except ExternalCodexRuntimeError as exc:
        raise ExternalCodexRuntimeError(
            "model_report_source_evidence_unavailable",
            f"model report source evidence cannot be inspected: {relative}",
        ) from exc
    _validate_evidence_anchor(
        raw,
        anchor,
        label=relative,
        error_code="model_report_source_evidence_anchor_invalid",
    )


def _validate_immutable_evidence_ref(
    value: str,
    state: Mapping[str, Any],
) -> None:
    """Resolve one stable immutable input identity and validate its exact bytes."""

    if not value.startswith("immutable:"):
        raise ExternalCodexRuntimeError(
            "model_report_evidence_scheme_unsupported",
            "model report immutable evidence must use the immutable: scheme",
        )
    body = value.removeprefix("immutable:")
    input_id, separator, anchor = body.partition("#")
    if (
        INPUT_ID_RE.fullmatch(input_id) is None
        or not separator
        or not anchor
        or "#" in anchor
    ):
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_invalid",
            "model report immutable evidence has an invalid input id or anchor",
        )
    matches = [
        item
        for item in state["materialized_task_inputs"]
        if item["input_id"] == input_id
    ]
    if len(matches) != 1:
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_unavailable",
            f"model report immutable evidence input is not materialized: {input_id}",
        )
    item = matches[0]
    candidate = Path(str(item["path"]))
    immutable_root = (
        Path(str(state["materialized_inputs"]["task"])).parent / "immutable"
    ).resolve()
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(immutable_root)
    except (OSError, ValueError) as exc:
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_unavailable",
            f"model report immutable evidence is absent or outside runtime inputs: {input_id}",
        ) from exc
    if resolved != candidate or candidate.is_symlink() or not candidate.is_file():
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_unavailable",
            f"model report immutable evidence is not a regular runtime input: {input_id}",
        )
    raw = read_bounded(candidate)
    if sha256_bytes(raw) != item["provenance"]["artifact_digest"]:
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_drift",
            f"model report immutable evidence bytes drifted: {input_id}",
        )
    _validate_evidence_anchor(
        raw,
        anchor,
        label=f"immutable input {input_id}",
        error_code="model_report_immutable_evidence_anchor_invalid",
    )


def _validate_runtime_evidence_ref(
    value: str,
    runtime_evidence_paths: Mapping[str, Path],
) -> None:
    """Validate one controller-produced artifact through a reserved identity."""

    if not value.startswith("runtime:"):
        raise ExternalCodexRuntimeError(
            "model_report_evidence_scheme_unsupported",
            "model report runtime evidence must use the runtime: scheme",
        )
    body = value.removeprefix("runtime:")
    evidence_id, separator, anchor = body.partition("#")
    if (
        evidence_id != "workspace-final-manifest"
        or not separator
        or not anchor
        or "#" in anchor
    ):
        raise ExternalCodexRuntimeError(
            "model_report_runtime_evidence_invalid",
            "model report runtime evidence names no admitted controller artifact",
        )
    candidate = runtime_evidence_paths.get(evidence_id)
    if (
        candidate is None
        or not candidate.is_absolute()
        or not candidate.is_file()
        or candidate.is_symlink()
    ):
        raise ExternalCodexRuntimeError(
            "model_report_runtime_evidence_unavailable",
            "model report final-workspace evidence is unavailable",
        )
    raw = read_bounded(candidate)
    _validate_evidence_anchor(
        raw,
        anchor,
        label="runtime workspace final manifest",
        error_code="model_report_runtime_evidence_anchor_invalid",
    )


def _validate_report_evidence_ref(
    value: str,
    *,
    state: Mapping[str, Any],
    source_evidence_paths: Sequence[str],
    runtime_evidence_paths: Mapping[str, Path],
) -> None:
    """Admit source, immutable-input, or reserved runtime evidence schemes."""

    if value.startswith("source:"):
        _validate_source_evidence_ref(
            value,
            state["workspace_path"],
            source_evidence_paths=source_evidence_paths,
        )
        return
    if value.startswith("immutable:"):
        _validate_immutable_evidence_ref(value, state)
        return
    if value.startswith("runtime:"):
        _validate_runtime_evidence_ref(value, runtime_evidence_paths)
        return
    raise ExternalCodexRuntimeError(
        "model_report_evidence_scheme_unsupported",
        "model report evidence must use anchored source:, immutable:<input_id>, "
        "or runtime:workspace-final-manifest refs",
    )


def _secret_shaped_path(value: str) -> bool:
    """Recognize paths that the controller must not content-inspect."""

    normalized = value.replace("\\", "/").strip()
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


def _shell_tokenizations(command: str) -> tuple[tuple[str, ...], ...]:
    """Return bounded outer and nested shell tokenizations for one event."""

    pending = [command]
    tokenizations: list[tuple[str, ...]] = []
    seen: set[str] = set()
    while pending and len(tokenizations) < 4:
        raw = pending.pop(0)
        if raw in seen:
            continue
        seen.add(raw)
        try:
            tokens = tuple(shlex.split(raw, posix=True))
        except ValueError:
            continue
        if not tokens:
            continue
        tokenizations.append(tokens)
        executable = Path(tokens[0]).name
        if executable in SHELL_NAMES:
            for index, token in enumerate(tokens[:-1]):
                if token in {"-c", "-lc"}:
                    pending.append(tokens[index + 1])
                    break
    return tuple(tokenizations)


def _command_segments(tokens: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    segments: list[tuple[str, ...]] = []
    current: list[str] = []
    for token in tokens:
        if token in SHELL_SEPARATORS:
            if current:
                segments.append(tuple(current))
                current = []
            continue
        current.append(token)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def _unwrap_command(segment: Sequence[str]) -> tuple[str, ...]:
    """Strip common non-effectful launch wrappers from one shell segment."""

    values = list(segment)
    while values:
        executable = Path(values[0]).name
        if executable in {"command", "exec"}:
            values = values[1:]
            continue
        if executable == "env":
            index = 1
            while index < len(values):
                token = values[index]
                if ENV_ASSIGNMENT_RE.match(token):
                    index += 1
                    continue
                if token in {"-i", "--ignore-environment", "-0", "--null"}:
                    index += 1
                    continue
                if token in {"-u", "--unset", "-C", "--chdir"}:
                    index += 2
                    continue
                if token.startswith(("--unset=", "--chdir=")):
                    index += 1
                    continue
                break
            if index < len(values) and values[index] == "--":
                index += 1
            values = values[index:]
            continue
        if executable == "timeout":
            index = 1
            while index < len(values) and values[index].startswith("-"):
                index += 1
            if index < len(values):
                index += 1
            values = values[index:]
            continue
        break
    return tuple(values)


def _git_subcommand(tokens: Sequence[str]) -> tuple[str | None, tuple[str, ...]]:
    index = 1
    options_with_value = {
        "-C",
        "-c",
        "--config-env",
        "--exec-path",
        "--git-dir",
        "--namespace",
        "--super-prefix",
        "--work-tree",
    }
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in options_with_value:
            index += 2
            continue
        if any(token.startswith(option + "=") for option in options_with_value if option.startswith("--")):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token, tuple(tokens[index + 1 :])
    if index < len(tokens):
        return tokens[index], tuple(tokens[index + 1 :])
    return None, ()


def _command_matches_argv(command: str, expected: Sequence[str]) -> bool:
    expected_tokens = tuple(str(value) for value in expected)
    for tokens in _shell_tokenizations(command):
        segments = _command_segments(tokens)
        if len(segments) == 1 and segments[0] == expected_tokens:
            return True
    return False


def _validation_cwd(workspace: str | Path, command_spec: Mapping[str, Any]) -> Path:
    root = Path(workspace).resolve()
    relative = str(command_spec["cwd"])
    candidate = root if relative == "." else root.joinpath(*relative.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ExternalCodexRuntimeError(
            "task_validation_cwd_invalid",
            "fixed validation cwd is absent or outside the exact workspace",
        ) from exc
    if not resolved.is_dir():
        raise ExternalCodexRuntimeError(
            "task_validation_cwd_invalid",
            "fixed validation cwd is not a workspace directory",
        )
    return resolved


def _validation_wrapper_argv(
    workspace: str | Path,
    command_spec: Mapping[str, Any],
) -> tuple[str, ...]:
    """Bind one fixed argv to an explicit, observable workspace cwd."""

    cwd = _validation_cwd(workspace, command_spec)
    return (
        "/usr/bin/env",
        "-C",
        str(cwd),
        "--",
        *(str(value) for value in command_spec["argv"]),
    )


def _annotate_validation_executions(
    commands: Sequence[Mapping[str, Any]],
    *,
    task: Mapping[str, Any],
    workspace: str | Path,
) -> list[dict[str, Any]]:
    """Attach runtime-derived argv/cwd provenance to exact validation events."""

    specs = tuple(task["validation_commands"])
    wrappers = tuple(_validation_wrapper_argv(workspace, item) for item in specs)
    annotated: list[dict[str, Any]] = []
    for item in commands:
        record = {
            key: value
            for key, value in item.items()
            if key
            not in {
                "validation_command_id",
                "validation_argv",
                "validation_cwd",
                "validation_wrapper_argv",
            }
        }
        command = str(record.get("command") or "")
        matches = [
            (spec, wrapper)
            for spec, wrapper in zip(specs, wrappers, strict=True)
            if _command_matches_argv(command, wrapper)
        ]
        if len(matches) > 1:
            raise ExternalCodexRuntimeError(
                "task_validation_command_ambiguous",
                "one command event matched multiple fixed validation identities",
            )
        if matches:
            spec, wrapper = matches[0]
            record.update(
                {
                    "validation_command_id": str(spec["command_id"]),
                    "validation_argv": [str(value) for value in spec["argv"]],
                    "validation_cwd": str(_validation_cwd(workspace, spec)),
                    "validation_wrapper_argv": list(wrapper),
                }
            )
        annotated.append(record)
    return annotated


def _command_effects(command: str) -> set[str]:
    """Classify high-risk command families without trusting shell spelling."""

    detected: set[str] = set()
    for tokenization in _shell_tokenizations(command):
        for raw_segment in _command_segments(tokenization):
            if not raw_segment:
                continue
            raw_executable = Path(raw_segment[0]).name.lower()
            if raw_executable in {"doas", "sudo"}:
                detected.add("global_config_mutation")
                segment = _unwrap_command(raw_segment[1:])
            else:
                segment = _unwrap_command(raw_segment)
            if not segment:
                if raw_executable == "env":
                    detected.add("secret_access")
                continue
            executable = Path(segment[0]).name.lower()
            args = tuple(value.lower() for value in segment[1:])

            if executable == "git":
                subcommand, git_args = _git_subcommand(segment)
                lowered = tuple(value.lower() for value in git_args)
                if subcommand == "commit":
                    detected.add("commit")
                elif subcommand == "push":
                    detected.add("push")
                elif subcommand == "merge":
                    detected.add("merge")
                elif subcommand == "tag":
                    detected.add("tag")
                elif subcommand == "config" and any(
                    value in {"--global", "--system"} for value in lowered
                ):
                    detected.add("global_config_mutation")
                elif subcommand == "credential":
                    detected.add("secret_access")
            elif executable == "gh":
                if any(args[index : index + 2] == ("pr", "create") for index in range(len(args))):
                    detected.add("pull_request")
                elif any(args[index : index + 2] == ("pr", "merge") for index in range(len(args))):
                    detected.add("merge")
                elif "release" in args:
                    detected.add("release")

            if (
                (executable in {"cargo", "npm", "pnpm"} and "publish" in args)
                or (executable == "yarn" and "publish" in args)
                or (executable == "twine" and args[:1] == ("upload",))
                or (executable in {"docker", "podman"} and "push" in args)
                or executable in {"scp", "sftp"}
                or (executable == "rsync" and any(":" in value for value in segment[1:]))
                or executable in {"curl", "wget"}
            ):
                detected.add("publication")

            if (
                executable == "systemctl"
                and any(
                    value
                    in {
                        "daemon-reload",
                        "disable",
                        "enable",
                        "mask",
                        "reload",
                        "restart",
                        "start",
                        "stop",
                        "unmask",
                    }
                    for value in args
                )
            ) or (
                executable in {"docker", "podman"}
                and any(
                    value
                    in {"down", "kill", "rm", "restart", "run", "start", "stop", "up"}
                    for value in args
                )
            ) or (
                executable == "kubectl"
                and args[:1]
                in {
                    ("apply",),
                    ("create",),
                    ("delete",),
                    ("patch",),
                    ("replace",),
                    ("rollout",),
                    ("scale",),
                }
            ) or executable in {"launchctl", "service", "supervisorctl"}:
                detected.add("service_mutation")

            if executable in {"op", "pass", "secret-tool", "vault"} or (
                executable in {"aws", "gcloud"}
                and any("secret" in value for value in args)
            ) or executable in {"printenv"}:
                detected.add("secret_access")
            if executable in READ_CAPABLE_COMMANDS and any(
                _secret_shaped_path(value)
                for value in segment[1:]
                if "/" in value or value.startswith(".")
            ):
                detected.add("secret_access")

            writes_system_path = any(
                value.startswith(SYSTEM_PATH_PREFIXES) for value in segment[1:]
            )
            sed_in_place = executable == "sed" and any(
                value == "-i"
                or value.startswith("-i")
                or value.startswith("--in-place")
                for value in args
            )
            if (
                executable in {"apt", "apt-get", "dnf", "pacman", "rpm", "yum"}
                or (executable == "pip" and "install" in args)
                or (executable == "cargo" and "install" in args)
                or (
                    executable in {"cp", "install", "ln", "mkdir", "mv", "rm", "tee"}
                    and writes_system_path
                )
                or (sed_in_place and writes_system_path)
            ):
                detected.add("global_config_mutation")
    return detected


def _command_has_unclassified_indirection(command: str) -> bool:
    """Identify executable command bodies that argv inspection cannot classify."""

    tokenizations = _shell_tokenizations(command)
    if not tokenizations:
        return True
    for tokenization in tokenizations:
        for raw_segment in _command_segments(tokenization):
            if not raw_segment:
                continue
            raw_executable = Path(raw_segment[0]).name.lower()
            if raw_executable in SHELL_NAMES:
                has_inline_body = any(
                    token in {"-c", "-lc"}
                    for token in raw_segment[:-1]
                )
                if not has_inline_body:
                    return True
                continue
            segment = _unwrap_command(raw_segment)
            if not segment:
                return True
            executable = Path(segment[0]).name.lower()
            args = tuple(value.lower() for value in segment[1:])
            if executable in OPAQUE_EFFECT_EXECUTABLES:
                return True
            if executable == "find" and any(
                value in {"-exec", "-execdir", "-ok", "-okdir"}
                for value in args
            ):
                return True
            if executable in {"eval", "xargs"}:
                return True
    return False


def _git_head(workspace: Path) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(workspace), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ExternalCodexRuntimeError(
            "workspace_not_git", "workspace is not an exact Git worktree"
        )
    return value


def _git_status(workspace: Path) -> dict[str, str]:
    completed = subprocess.run(
        [
            "/usr/bin/git",
            "-c",
            "core.quotePath=false",
            "-C",
            str(workspace),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ExternalCodexRuntimeError(
            "workspace_status_failed", "cannot inspect exact workspace status"
        )
    status: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if len(line) < 4:
            continue
        code = line[:2]
        path = line[3:].split(" -> ")[-1]
        status[path] = code
    return status


def _git_bytes(workspace: Path, *args: str, timeout: int = 30) -> bytes:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(workspace), *args],
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise ExternalCodexRuntimeError(
            "workspace_manifest_failed",
            f"cannot inspect workspace manifest input: git {' '.join(args)}",
        )
    return completed.stdout


def _nul_paths(payload: bytes, *, label: str) -> tuple[str, ...]:
    values: list[str] = []
    for raw in payload.split(b"\0"):
        if not raw:
            continue
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_path_invalid",
                f"{label} contains a non-UTF-8 path",
            ) from exc
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_path_invalid",
                f"{label} contains an unsafe path",
            )
        values.append(path.as_posix())
    return tuple(values)


def _tracked_index_flags(workspace: Path) -> dict[str, tuple[str, ...]]:
    flags: dict[str, tuple[str, ...]] = {}
    for raw in _git_bytes(workspace, "ls-files", "--stage", "-z").split(b"\0"):
        if not raw:
            continue
        try:
            metadata, raw_path = raw.split(b"\t", 1)
            mode = metadata.split(b" ", 1)[0]
            paths = _nul_paths(raw_path + b"\0", label="tracked index entries")
        except (ValueError, ExternalCodexRuntimeError) as exc:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "git ls-files returned an invalid staged index record",
            ) from exc
        if len(paths) != 1:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "git ls-files returned an invalid staged path",
            )
        if mode == b"160000":
            raise ExternalCodexRuntimeError(
                "workspace_submodule_unsupported",
                f"workspace manifest does not yet admit tracked submodule {paths[0]}",
            )
    for raw in _git_bytes(workspace, "ls-files", "-v", "-z").split(b"\0"):
        if not raw:
            continue
        if len(raw) < 3 or raw[1:2] != b" ":
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "git ls-files returned an invalid tracked-path record",
            )
        tag = chr(raw[0])
        paths = _nul_paths(raw[2:] + b"\0", label="tracked files")
        if len(paths) != 1:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "git ls-files returned an invalid tracked path",
            )
        values: list[str] = []
        if tag.islower():
            values.append("assume_unchanged")
        if tag.upper() == "S":
            values.append("skip_worktree")
        flags[paths[0]] = tuple(values)
    return flags


def build_workspace_manifest(workspace: str | Path) -> dict[str, Any]:
    """Describe exact HEAD plus every tracked, untracked, or ignored byte."""

    location = Path(workspace).resolve()
    if not location.is_dir():
        raise ExternalCodexRuntimeError(
            "workspace_unavailable", "workspace manifest target is unavailable"
        )
    status_raw = _git_bytes(
        location,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    diff_raw = _git_bytes(location, "diff", "--binary", "HEAD", "--", timeout=60)
    changed = _nul_paths(
        _git_bytes(location, "diff", "--name-only", "-z", "HEAD", "--"),
        label="tracked diff",
    )
    untracked = _nul_paths(
        _git_bytes(
            location,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ),
        label="untracked files",
    )
    ignored = _nul_paths(
        _git_bytes(
            location,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
        ),
        label="ignored files",
    )
    tracked_flags = _tracked_index_flags(location)
    for relative in sorted(set(untracked) | set(ignored)):
        if _secret_shaped_path(relative):
            raise ExternalCodexRuntimeError(
                "workspace_secret_path_present",
                "workspace contains an untracked or ignored secret-shaped path",
            )
    entries: list[dict[str, Any]] = []
    all_paths = set(tracked_flags) | set(changed) | set(untracked) | set(ignored)
    for relative in sorted(all_paths):
        path = location / relative
        index_flags = list(tracked_flags.get(relative, ()))
        if path.is_symlink():
            target = os.readlink(path).encode("utf-8")
            entries.append(
                {
                    "path": relative,
                    "kind": "symlink",
                    "size_bytes": len(target),
                    "sha256": sha256_bytes(target),
                    "index_flags": index_flags,
                }
            )
        elif path.is_file():
            resolved = path.resolve()
            try:
                resolved.relative_to(location)
            except ValueError as exc:
                raise ExternalCodexRuntimeError(
                    "workspace_manifest_path_invalid",
                    "workspace manifest would traverse a linked parent",
                ) from exc
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(resolved),
                    "index_flags": index_flags,
                }
            )
        elif path.is_dir():
            entries.append(
                {
                    "path": relative,
                    "kind": "directory",
                    "size_bytes": 0,
                    "sha256": None,
                    "index_flags": index_flags,
                }
            )
        else:
            entries.append(
                {
                    "path": relative,
                    "kind": "missing",
                    "size_bytes": 0,
                    "sha256": None,
                    "index_flags": index_flags,
                }
            )
    status = _git_status(location)
    return {
        "$schema": "schemas/external-codex-workspace-manifest.schema.json",
        "schema_version": "abyss_stack_external_codex_workspace_manifest_v1",
        "workspace_path": str(location),
        "git_head": _git_head(location),
        "git_status_porcelain_sha256": sha256_bytes(status_raw),
        "git_diff_binary_sha256": sha256_bytes(diff_raw),
        "status_entries": [
            {"path": path, "status": status[path]} for path in sorted(status)
        ],
        "content_entries": entries,
    }


def assert_workspace_manifest(
    manifest: Mapping[str, Any], workspace: str | Path
) -> None:
    validate_json(
        manifest,
        WORKSPACE_MANIFEST_SCHEMA_PATH,
        label="external Codex workspace manifest",
    )
    expected = build_workspace_manifest(workspace)
    if manifest != expected:
        raise ExternalCodexRuntimeError(
            "workspace_manifest_drift",
            "workspace bytes differ from the exact immutable baseline manifest",
        )


def compare_workspace_manifest(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, str]]:
    """Return byte-aware workspace changes relative to one exact manifest."""

    baseline_status = {
        str(item["path"]): str(item["status"])
        for item in baseline.get("status_entries", [])
    }
    current_status = {
        str(item["path"]): str(item["status"])
        for item in current.get("status_entries", [])
    }
    baseline_content = {
        str(item["path"]): dict(item)
        for item in baseline.get("content_entries", [])
    }
    current_content = {
        str(item["path"]): dict(item)
        for item in current.get("content_entries", [])
    }
    changed: list[dict[str, str]] = []
    if baseline.get("git_head") != current.get("git_head"):
        changed.append({"path": "<git-head>", "status": "head_changed"})
    for path in sorted(
        set(baseline_status)
        | set(current_status)
        | set(baseline_content)
        | set(current_content)
    ):
        if baseline_status.get(path) != current_status.get(path):
            changed.append(
                {"path": path, "status": current_status.get(path, "cleaned")}
            )
        elif baseline_content.get(path) != current_content.get(path):
            status = (
                "created"
                if path not in baseline_content
                else "removed"
                if path not in current_content
                else "content_changed"
            )
            changed.append({"path": path, "status": status})
    if baseline != current and not changed:
        changed.append(
            {"path": "<workspace-manifest>", "status": "manifest_changed"}
        )
    return changed


def _changed_since(
    baseline: Mapping[str, str], current: Mapping[str, str]
) -> list[dict[str, str]]:
    paths = sorted(set(baseline) | set(current))
    return [
        {"path": path, "status": current.get(path, "cleaned")}
        for path in paths
        if baseline.get(path) != current.get(path)
    ]


def _model_catalog_entry(value: Any, model_slug: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("slug") == model_slug:
            return value
        for nested in value.values():
            found = _model_catalog_entry(nested, model_slug)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _model_catalog_entry(nested, model_slug)
            if found is not None:
                return found
    return None


def _command_text(item: Mapping[str, Any]) -> str | None:
    for key in ("command", "cmd"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


class ExternalCodexRuntime:
    """Persistent launch, event, resume, and A2A-export controller."""

    def __init__(
        self,
        state_root: str | Path,
        *,
        profile_path: str | Path = PROFILE_PATH,
    ) -> None:
        self.state_root = Path(state_root)
        if not self.state_root.is_absolute():
            raise ExternalCodexRuntimeError(
                "invalid_state_root", "external Codex state root must be absolute"
            )
        if self.state_root.is_symlink():
            raise ExternalCodexRuntimeError(
                "invalid_state_root", "external Codex state root cannot be a symlink"
            )
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.state_root.is_dir():
            raise ExternalCodexRuntimeError(
                "invalid_state_root", "external Codex state root is not a directory"
            )
        self.profile_path = Path(profile_path)
        self.profile_raw = read_bounded(self.profile_path)
        self.profile = load_json_bytes(self.profile_raw, label="runtime profile")
        validate_json(self.profile, PROFILE_SCHEMA_PATH, label="runtime profile")
        for label, values, key in (
            ("tool profile", self.profile["tool_profiles"], "profile_id"),
        ):
            identities = [item[key] for item in values]
            if len(identities) != len(set(identities)):
                raise ExternalCodexRuntimeError(
                    "runtime_profile_ambiguous", f"{label} identities must be unique"
                )
        if self.profile["result_schema_ref"] != (
            "schemas/external-codex-report.schema.json"
        ):
            raise ExternalCodexRuntimeError(
                "runtime_profile_invalid", "runtime profile result schema ref drifted"
            )
        validate_structured_output_schema(load_schema(REPORT_SCHEMA_PATH))

    def _session_dir(self, session_id: str) -> Path:
        return self.state_root / "sessions" / _session_token(session_id)

    @contextmanager
    def _lock(self, session_id: str) -> Iterator[None]:
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        lock_path = session_dir / "session.lock"
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _state_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "state.json"

    def _load_state(self, session_id: str) -> dict[str, Any]:
        path = self._state_path(session_id)
        if not path.is_file():
            raise ExternalCodexRuntimeError(
                "session_not_found", f"external Codex session is unknown: {session_id}"
            )
        state = load_json(path, label="runtime state")
        validate_json(state, STATE_SCHEMA_PATH, label="runtime state")
        if (
            state.get("schema_version")
            not in {LEGACY_STATE_SCHEMA_VERSION, STATE_SCHEMA_VERSION}
            or state.get("session_id") != session_id
        ):
            raise ExternalCodexRuntimeError(
                "runtime_state_invalid", "external Codex state identity is invalid"
            )
        return self._recover_or_verify_event_state(state)

    def _recover_or_verify_event_state(
        self, state: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Verify the normalized stream or recover one strict append extension."""

        session_id = str(state["session_id"])
        path = self._events_path(session_id)
        last_sequence = int(state["last_event_sequence"])
        if not path.exists():
            if last_sequence != -1:
                raise ExternalCodexRuntimeError(
                    "runtime_event_state_drift",
                    "runtime event stream is missing behind durable state",
                )
        durable_count = last_sequence + 1
        digest = hashlib.sha256()
        prefix_digest = sha256_bytes(b"") if durable_count == 0 else None
        line_count = 0
        extension_events: list[dict[str, Any]] = []
        if path.exists():
            for line_number, line in _iter_jsonl_bytes(
                path,
                failure_code="runtime_event_state_drift",
                label="runtime event stream",
            ):
                try:
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ExternalCodexRuntimeError(
                        "runtime_event_state_drift",
                        f"runtime event line {line_number} is invalid",
                    ) from exc
                validate_json(
                    event, EVENT_SCHEMA_PATH, label="normalized runtime event"
                )
                if (
                    event.get("sequence") != line_count
                    or event.get("session_id") != session_id
                ):
                    raise ExternalCodexRuntimeError(
                        "runtime_event_state_drift",
                        f"runtime event line {line_number} is not contiguous or owned",
                    )
                if line_count >= durable_count:
                    extension_events.append(event)
                digest.update(line)
                line_count += 1
                if line_count == durable_count:
                    prefix_digest = "sha256:" + digest.hexdigest()
        if line_count < durable_count:
            raise ExternalCodexRuntimeError(
                "runtime_event_state_drift",
                "runtime event stream was truncated behind durable state",
            )
        current_digest = "sha256:" + digest.hexdigest()
        recorded_digest = state.get("events_digest")
        if line_count == durable_count:
            if isinstance(recorded_digest, str) and recorded_digest != current_digest:
                raise ExternalCodexRuntimeError(
                    "runtime_event_state_drift",
                    "runtime event bytes differ from their durable state digest",
                )
            if recorded_digest == current_digest:
                return dict(state)
        else:
            if not isinstance(recorded_digest, str):
                raise ExternalCodexRuntimeError(
                    "runtime_event_state_drift",
                    "runtime event extension has no trusted durable prefix digest",
                )
            if prefix_digest != recorded_digest:
                raise ExternalCodexRuntimeError(
                    "runtime_event_state_drift",
                    "runtime event extension rewrites its durable prefix",
                )
        recovered = dict(state)
        for event in extension_events:
            self._apply_recovered_codex_event_state(recovered, event)
        recovered["last_event_sequence"] = line_count - 1
        recovered["events_digest"] = current_digest
        validate_json(recovered, STATE_SCHEMA_PATH, label="recovered runtime state")
        _atomic_write_json(self._state_path(session_id), recovered)
        return recovered

    def _apply_recovered_codex_event_state(
        self,
        state: dict[str, Any],
        event: Mapping[str, Any],
    ) -> None:
        """Replay the semantic delta carried by one durable Codex event."""

        source_type = event.get("source_event_type")
        if not isinstance(source_type, str) or not event.get("event_type", "").startswith(
            "codex."
        ):
            return
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != source_type:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "recovered Codex event differs from its normalized source type",
            )
        delta = payload.get("_runtime_state_delta_v1")
        if not isinstance(delta, dict):
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_incomplete",
                "durable Codex event has no replayable semantic state delta",
            )
        self._apply_codex_state_delta(
            state,
            attempt_id=str(event["attempt_id"]),
            source_type=source_type,
            source_payload=payload,
            delta=delta,
        )

    def _save_state(self, state: Mapping[str, Any]) -> None:
        candidate = dict(state)
        events_path = self._events_path(str(candidate["session_id"]))
        if events_path.exists():
            candidate["events_digest"] = sha256_file(events_path)
        elif int(candidate["last_event_sequence"]) == -1:
            candidate["events_digest"] = sha256_bytes(b"")
        else:
            raise ExternalCodexRuntimeError(
                "runtime_event_state_drift",
                "cannot save runtime state without its normalized event stream",
            )
        validate_json(candidate, STATE_SCHEMA_PATH, label="runtime state")
        _atomic_write_json(
            self._state_path(str(candidate["session_id"])), candidate
        )

    def _failure_closeout_context(
        self,
        *,
        binding: AgentIncarnationBinding,
        task: Mapping[str, Any],
        materialized_inputs: Mapping[str, str],
    ) -> dict[str, Any]:
        """Freeze source-independent failure evidence and wake semantics."""

        return {
            "target_owner": task["target_owner"],
            "task_ref": _artifact_ref(
                Path(materialized_inputs["task"]),
                owner=str(task["target_owner"]),
            ),
            "incarnation_binding_ref": _artifact_ref(
                Path(materialized_inputs["incarnation_binding"]),
                owner="aoa-sdk",
            ),
            "wake_evaluations": {
                status: self._wake_evaluation(binding, status)
                for status in ("failed", "authority_blocked")
            },
        }

    def _events_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "events.jsonl"

    def _append_event(
        self,
        state: dict[str, Any],
        *,
        event_type: str,
        payload: Mapping[str, Any],
        attempt_id: str | None = None,
        thread_id: str | None = None,
        source_event_type: str | None = None,
        significance: Literal[
            "trace",
            "progress",
            "checkpoint",
            "review",
            "authority",
            "parent_wake",
            "terminal",
        ] = "trace",
    ) -> dict[str, Any]:
        sequence = int(state.get("last_event_sequence", -1)) + 1
        event = {
            "schema_version": "abyss_stack_external_codex_event_v1",
            "sequence": sequence,
            "recorded_at": iso_now(),
            "session_id": state["session_id"],
            "attempt_id": attempt_id or str(state.get("active_attempt_id") or "runtime"),
            "thread_id": thread_id if thread_id is not None else state.get("thread_id"),
            "event_type": event_type,
            "source_event_type": source_event_type,
            "payload_digest": canonical_digest(payload),
            "significance": significance,
            "payload": dict(payload),
        }
        validate_json(event, EVENT_SCHEMA_PATH, label="normalized runtime event")
        _append_jsonl(self._events_path(str(state["session_id"])), event)
        state["last_event_sequence"] = sequence
        return event

    def _load_coordinate(
        self,
        launch: Mapping[str, Any],
        key: str,
    ) -> tuple[Path, bytes, dict[str, Any]]:
        coordinate = launch[key]
        path = Path(str(coordinate["path"]))
        raw = read_bounded(path)
        if sha256_bytes(raw) != coordinate["digest"]:
            raise ExternalCodexRuntimeError(
                "artifact_digest_mismatch", f"{key} bytes differ from launch digest"
            )
        return path, raw, load_json_bytes(raw, label=key)

    def _validate_owner_contour_admission(
        self,
        *,
        owner_request_path: Path,
        launch: Mapping[str, Any],
        launch_raw: bytes,
        coordinates: Mapping[str, tuple[Path, bytes, dict[str, Any]]],
        plan: RunPlan,
        binding: AgentIncarnationBinding,
        task: Mapping[str, Any],
        immutable_inputs: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        request_schema_coordinate = launch["owner_execution_request_schema"]
        dag_schema_coordinate = launch["task_local_dag_schema"]
        for key, coordinate in (
            ("owner_execution_request_schema", request_schema_coordinate),
            ("task_local_dag_schema", dag_schema_coordinate),
        ):
            delivered_identity = {
                field: coordinate[field]
                for field in (
                    "owner_repo",
                    "artifact_ref",
                    "source_ref",
                    "digest",
                    "schema_version",
                )
            }
            if delivered_identity != self.profile["owner_contracts"][key]:
                raise ExternalCodexRuntimeError(
                    "owner_admission_schema_identity_invalid",
                    "owner-contour schema differs from the runtime-profile-pinned owner source",
                )
        owner_request_raw = read_bounded(owner_request_path)
        owner_request = load_json_bytes(
            owner_request_raw, label="aoa-agents external execution request"
        )
        validate_json(
            owner_request,
            coordinates["owner_execution_request_schema"][0],
            label="aoa-agents external execution request",
        )
        if (
            owner_request.get("intent") != "execute"
            or owner_request.get("summon_request", {}).get("transport_preference")
            != "external_cli"
        ):
            raise ExternalCodexRuntimeError(
                "owner_execution_request_not_executable",
                "owner-contour admission requires an execute request for external_cli",
            )
        external = owner_request["external_incarnation"]
        if (
            external["runtime_interface"]
            != "abyss_stack_external_codex_agent_v1"
            or external["launches_separate_os_process"] is not True
            or external["uses_builtin_codex_subagents"] is not False
            or external["separate_cli_session"] is not True
            or external["usage_metering"] != "observe_only_no_budget"
        ):
            raise ExternalCodexRuntimeError(
                "owner_execution_runtime_mismatch",
                "owner request does not admit this external process/session runtime",
            )

        def exact_input(content_ref: Mapping[str, Any], *, label: str) -> Mapping[str, Any]:
            matches = [
                item
                for item in immutable_inputs
                if item["provenance"].owner_repo == content_ref["owner_repo"]
                and item["provenance"].artifact_ref == content_ref["object_id"]
                and item["provenance"].schema_version == content_ref["schema_version"]
                and item["provenance"].artifact_digest == content_ref["digest"]
            ]
            if len(matches) != 1:
                raise ExternalCodexRuntimeError(
                    "owner_content_ref_unbound",
                    f"{label} is not one exact continuation-bound immutable input",
                )
            return matches[0]

        obligation_input = exact_input(
            external["obligation_ref"], label="agent obligation"
        )
        mandate_input = exact_input(
            external["actor_mandate_ref"], label="actor mandate"
        )
        dag_input = exact_input(external["task_local_dag_ref"], label="task-local DAG")
        transfer_input = exact_input(
            external["responsibility_transfer_ref"],
            label="responsibility transfer",
        )
        for index, procedure_ref in enumerate(external["domain_procedure_refs"]):
            exact_input(procedure_ref, label=f"domain procedure {index + 1}")

        dag = load_json_bytes(dag_input["raw"], label="task-local DAG")
        validate_json(
            dag,
            coordinates["task_local_dag_schema"][0],
            label="task-local DAG",
        )
        if dag.get("status") != "ready" or dag.get("authority") is not False:
            raise ExternalCodexRuntimeError(
                "task_local_dag_not_ready",
                "owner-contour launch requires a ready non-authoritative task-local DAG",
            )

        transfer = load_json_bytes(
            transfer_input["raw"], label="responsibility transfer"
        )
        transfer_holders = transfer.get("holder_ids")
        if transfer_holders is None:
            transfer_holders = [
                transfer.get("prior_holder"),
                transfer.get("current_holder"),
            ]
        if (
            transfer.get("schema_version") != "responsibility-transfer-v1"
            or transfer.get("state")
            != external["responsibility_transfer_ref"]["admitted_state"]
            or transfer_holders
            != external["responsibility_transfer_ref"]["holder_ids"]
            or transfer.get("obligation_ref")
            != external["obligation_ref"]["object_id"]
            or transfer.get("mandate_ref")
            != external["actor_mandate_ref"]["object_id"]
            or transfer.get("task_local_dag_ref")
            != external["task_local_dag_ref"]["object_id"]
            or transfer.get("return_owner") != owner_request["return_owner"]
        ):
            raise ExternalCodexRuntimeError(
                "responsibility_transfer_content_mismatch",
                "responsibility-transfer bytes do not prove the admitted holder transition",
            )

        obligation = load_json_bytes(
            obligation_input["raw"], label="agent obligation"
        )
        if (
            obligation.get("schema_version") != "agent-obligation-v1"
            or obligation.get("obligation_id")
            != external["obligation_ref"]["object_id"]
            or obligation.get("goal_anchor") != task["parent_task_id"]
            or obligation.get("domain_owner") != task["target_owner"]
            or obligation.get("current_holder") != transfer_holders[0]
            or obligation.get("return_owner") != owner_request["return_owner"]
        ):
            raise ExternalCodexRuntimeError(
                "agent_obligation_content_mismatch",
                "agent-obligation bytes differ from the admitted duty and transfer",
            )

        mandate = load_json_bytes(mandate_input["raw"], label="actor mandate")
        if (
            mandate.get("schema_version") != "actor-mandate-v1"
            or mandate.get("mandate_id")
            != external["actor_mandate_ref"]["object_id"]
            or mandate.get("role_id") != binding.role_id
            or mandate.get("obligation_ref")
            != external["obligation_ref"]["object_id"]
            or mandate.get("domain_procedure_refs")
            != [
                item["object_id"]
                for item in external["domain_procedure_refs"]
            ]
            or mandate.get("return_owner") != owner_request["return_owner"]
            or mandate.get("stop_line") != owner_request["child_stop_line"]
        ):
            raise ExternalCodexRuntimeError(
                "actor_mandate_content_mismatch",
                "actor-mandate bytes differ from the admitted obligation, role, or procedure",
            )

        mandate_ref = external["actor_mandate_ref"]
        if (
            mandate_input["raw"] != coordinates["role_contract"][1]
            or binding.role_contract_ref.owner_repo != "aoa-agents"
            or binding.role_contract_ref.artifact_ref != mandate_ref["object_id"]
            or binding.role_contract_ref.schema_version != "actor-mandate-v1"
            or launch["role_contract"]["digest"] != mandate_ref["digest"]
        ):
            raise ExternalCodexRuntimeError(
                "actor_mandate_binding_mismatch",
                "incarnation role contract is not the exact admitted actor mandate",
            )

        incarnation_ref = external["incarnation_binding_ref"]
        if (
            incarnation_ref["object_id"] != binding.provenance.artifact_ref
            or incarnation_ref["digest"] != launch["incarnation_binding"]["digest"]
        ):
            raise ExternalCodexRuntimeError(
                "owner_incarnation_binding_mismatch",
                "owner request names another incarnation binding",
            )
        sdk_request_ref = external["sdk_summon_request_ref"]
        if (
            sdk_request_ref["object_id"] != binding.task_request_ref.artifact_ref
            or sdk_request_ref["digest"] != binding.task_request_ref.artifact_digest
            or sdk_request_ref["schema_version"]
            != binding.task_request_ref.schema_version
        ):
            raise ExternalCodexRuntimeError(
                "owner_sdk_request_mismatch",
                "owner request names another canonical SDK summon request",
            )
        sdk_decision_ref = external["sdk_summon_decision_ref"]
        decision_matches = [
            item
            for item in plan.snapshot.source_refs
            if item.owner_repo == sdk_decision_ref["owner_repo"]
            and item.artifact_ref == sdk_decision_ref["object_id"]
            and item.schema_version == sdk_decision_ref["schema_version"]
            and item.artifact_digest == sdk_decision_ref["digest"]
        ]
        if len(decision_matches) != 1:
            raise ExternalCodexRuntimeError(
                "owner_sdk_decision_mismatch",
                "owner request names no exact plan-bound SDK summon decision",
            )
        exact_input(sdk_decision_ref, label="SDK summon decision")

        runtime_launch_ref = external["runtime_launch_ref"]
        if (
            runtime_launch_ref["object_id"] != launch["launch_id"]
            or runtime_launch_ref["digest"] != sha256_bytes(launch_raw)
        ):
            raise ExternalCodexRuntimeError(
                "owner_runtime_launch_mismatch",
                "owner request does not bind these exact launch bytes",
            )
        continuity_ref = external["continuity_ref"]
        continuity_is_binding = (
            continuity_ref["object_id"] == binding.continuation.continuation_id
            and continuity_ref["digest"] == launch["incarnation_binding"]["digest"]
        )
        if not continuity_is_binding:
            exact_input(continuity_ref, label="continuity")
        event_ref = external["return_event_schema_ref"]
        if (
            event_ref["digest"] != sha256_bytes(read_bounded(EVENT_SCHEMA_PATH))
            or event_ref["schema_version"] != "abyss_stack_external_codex_event_v1"
        ):
            raise ExternalCodexRuntimeError(
                "owner_return_event_schema_mismatch",
                "owner request names another runtime return-event ABI",
            )
        if (
            owner_request["summon_request"].get("desired_role")
            not in {None, binding.role_id}
            or owner_request["summon_request"].get("child_agent_id")
            not in {None, binding.incarnation_id}
            or owner_request["summon_request"].get("parent_task_id")
            not in {None, task["parent_task_id"]}
        ):
            raise ExternalCodexRuntimeError(
                "owner_request_identity_mismatch",
                "owner request role, child, or parent identity differs from the incarnation",
            )
        child_scope = owner_request["child_scope"]
        expected_outputs = set(str(item) for item in owner_request["expected_outputs"])
        if (
            child_scope["task"] != task["objective"]
            or set(child_scope["allowed_tools"])
            != set(binding.tool_profile.required_tool_ids)
            or child_scope["allowed_effects"] != [task["allowed_effect_class"]]
            or "external_codex_agent_result" not in expected_outputs
            or not set(task["expected_artifacts"]).issubset(expected_outputs)
        ):
            raise ExternalCodexRuntimeError(
                "owner_request_scope_mismatch",
                "owner request task, tools, effects, or named outputs differ from the bound duty",
            )
        return {
            "path": owner_request_path,
            "raw": owner_request_raw,
            "request": owner_request,
            "request_digest": sha256_bytes(owner_request_raw),
            "obligation_ref": external["obligation_ref"],
            "mandate_ref": mandate_ref,
            "dag_ref": external["task_local_dag_ref"],
            "transfer_ref": external["responsibility_transfer_ref"],
        }

    def _codex_preflight(
        self,
        launch: Mapping[str, Any],
        model_slug: str,
        reasoning_effort: str,
        tool_entry: Mapping[str, Any],
    ) -> dict[str, Any]:
        executable = Path(str(launch["codex_executable"]))
        if not executable.is_absolute() or not executable.is_file():
            raise ExternalCodexRuntimeError(
                "codex_unavailable", "Codex executable is not an absolute regular file"
            )
        if executable.resolve() != executable:
            raise ExternalCodexRuntimeError(
                "codex_executable_not_resolved",
                "Codex executable must be the resolved binary, not a symlink",
            )
        executable_digest = sha256_bytes(read_bounded(executable, limit=512 * 1024 * 1024))
        if executable_digest != launch["codex_executable_digest"]:
            raise ExternalCodexRuntimeError(
                "codex_executable_drift", "Codex executable digest changed"
            )
        containment = self.profile["process_containment"]
        containment_paths = {
            "supervisor": PART_ROOT / str(containment["supervisor_ref"]),
            "probe_executable": Path(str(containment["probe_executable"])),
            "python_executable": Path(sys.executable).resolve(),
        }
        for label, path in containment_paths.items():
            if (
                not path.is_absolute()
                or not path.is_file()
                or path.resolve() != path
                or (label != "supervisor" and not os.access(path, os.X_OK))
            ):
                raise ExternalCodexRuntimeError(
                    "process_containment_unavailable",
                    f"configured {label} is not an exact executable",
                )
        if containment_paths["supervisor"] != SUPERVISOR_PATH:
            raise ExternalCodexRuntimeError(
                "process_containment_unavailable",
                "runtime profile selected an unexpected supervisor source",
            )
        env = self._codex_environment(launch, self.state_root, tool_entry)
        probes: list[tuple[str, list[str]]] = [
            ("version", [str(executable), "--version"]),
            ("login", [str(executable), "login", "status"]),
            ("models", [str(executable), "debug", "models", "--bundled"]),
        ]
        results: dict[str, subprocess.CompletedProcess[str]] = {}
        for label, command in probes:
            try:
                completed = subprocess.run(
                    command,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=30,
                    env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ExternalCodexRuntimeError(
                    "codex_preflight_failed", f"Codex {label} probe failed"
                ) from exc
            if completed.returncode != 0:
                raise ExternalCodexRuntimeError(
                    "codex_preflight_failed", f"Codex {label} probe was rejected"
                )
            results[label] = completed
        version = results["version"].stdout.strip()
        expected_version = (
            "codex-cli " + self.profile["model_admission"]["runtime_version"]
        )
        if (
            self.profile["codex_cli"]["required_version"] != expected_version
            or version != expected_version
        ):
            raise ExternalCodexRuntimeError(
                "codex_version_mismatch",
                f"runtime requires {expected_version}, got {version}",
            )
        login_output = results["login"].stdout + results["login"].stderr
        if "Logged in using ChatGPT" not in login_output:
            raise ExternalCodexRuntimeError(
                "codex_auth_unavailable", "required ChatGPT Codex login is unavailable"
            )
        try:
            catalog = json.loads(results["models"].stdout)
        except json.JSONDecodeError as exc:
            raise ExternalCodexRuntimeError(
                "codex_model_catalog_invalid", "Codex model catalog is invalid JSON"
            ) from exc
        entry = _model_catalog_entry(catalog, model_slug)
        efforts = {
            item.get("effort")
            for item in (entry or {}).get("supported_reasoning_levels", [])
            if isinstance(item, dict)
        }
        if entry is None or reasoning_effort not in efforts:
            raise ExternalCodexRuntimeError(
                "codex_model_unavailable",
                f"{model_slug} effort {reasoning_effort} is absent from the live catalog",
            )
        containment_probe = self._containment_command(
            [str(containment_paths["probe_executable"])]
        )
        try:
            contained = subprocess.run(
                containment_probe,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExternalCodexRuntimeError(
                "process_containment_unavailable",
                "Linux subreaper-supervisor containment probe failed",
            ) from exc
        if contained.returncode != 0:
            raise ExternalCodexRuntimeError(
                "process_containment_unavailable",
                "Linux subreaper-supervisor containment probe was rejected",
            )
        return {
            "version": version,
            "auth_regime": "chatgpt_login",
            "model_slug": model_slug,
            "reasoning_effort": reasoning_effort,
            "executable_digest": executable_digest,
        }

    def _containment_command(
        self,
        command: Sequence[str],
        *,
        identity_path: Path | None = None,
    ) -> list[str]:
        containment = self.profile["process_containment"]
        if containment["strategy"] != "linux_subreaper_supervisor_v1":
            raise ExternalCodexRuntimeError(
                "process_containment_unavailable",
                "runtime profile selected an unsupported process-containment strategy",
            )
        supervisor_argv = [
            str(Path(sys.executable).resolve()),
            str(SUPERVISOR_PATH),
            "--parent-pid",
            str(os.getpid()),
            "--term-timeout-seconds",
            str(containment["term_timeout_seconds"]),
            "--kill-timeout-seconds",
            str(containment["kill_timeout_seconds"]),
        ]
        if identity_path is not None:
            if not identity_path.is_absolute():
                raise ExternalCodexRuntimeError(
                    "codex_process_identity_invalid",
                    "process identity receipt path must be absolute",
                )
            supervisor_argv.extend(("--identity-file", str(identity_path)))
        return [*supervisor_argv, "--", *command]

    def _validate_launch(
        self,
        launch_path: Path,
        *,
        owner_request_path: Path | None = None,
    ) -> dict[str, Any]:
        launch_raw = read_bounded(launch_path)
        launch = load_json_bytes(launch_raw, label="external Codex launch")
        if launch.get("admission_class") == "owner_contour" and owner_request_path is None:
            raise ExternalCodexRuntimeError(
                "owner_contour_admission_unbound",
                "owner_contour requires the separate aoa-agents execution request",
            )
        validate_json(launch, LAUNCH_SCHEMA_PATH, label="external Codex launch")
        if (
            launch["admission_class"] == "transport_study_fixture"
            and owner_request_path is not None
        ):
            raise ExternalCodexRuntimeError(
                "fixture_owner_admission_forbidden",
                "transport fixtures cannot be promoted by attaching an owner request",
            )
        coordinates: dict[str, tuple[Path, bytes, dict[str, Any]]] = {}
        coordinate_keys = [
            "plan",
            "incarnation_binding",
            "model_realization",
            "task",
            "runtime_profile",
            "role_contract",
            "result_schema",
        ]
        if launch["admission_class"] == "owner_contour":
            coordinate_keys.extend(
                ("owner_execution_request_schema", "task_local_dag_schema")
            )
        for key in coordinate_keys:
            coordinates[key] = self._load_coordinate(launch, key)

        if coordinates["runtime_profile"][1] != self.profile_raw:
            raise ExternalCodexRuntimeError(
                "runtime_profile_mismatch", "launch profile is not this runtime profile"
            )
        plan = RunPlan.model_validate(coordinates["plan"][2])
        binding = AgentIncarnationBinding.model_validate(
            coordinates["incarnation_binding"][2]
        )
        assert_agent_incarnation_binding_matches_plan(binding, plan)
        task = coordinates["task"][2]
        validate_json(task, TASK_SCHEMA_PATH, label="external Codex task")
        validation_command_ids = [
            str(item["command_id"]) for item in task["validation_commands"]
        ]
        if len(validation_command_ids) != len(set(validation_command_ids)):
            raise ExternalCodexRuntimeError(
                "task_validation_command_duplicate",
                "task validation command ids must be unique",
            )
        if any(item["cwd"] != "." for item in task["validation_commands"]):
            raise ExternalCodexRuntimeError(
                "task_validation_cwd_unsupported",
                "fixed validation commands must execute from the exact workspace root",
            )
        validation_signatures = [
            (str(item["cwd"]), tuple(str(value) for value in item["argv"]))
            for item in task["validation_commands"]
        ]
        if len(validation_signatures) != len(set(validation_signatures)):
            raise ExternalCodexRuntimeError(
                "task_validation_command_ambiguous",
                "fixed validation argv/cwd pairs must be unique",
            )
        for item in task["validation_commands"]:
            _validation_wrapper_argv(launch["workspace_path"], item)
        realization = coordinates["model_realization"][2]

        exact_refs = (
            (binding.role_contract_ref, "role_contract"),
            (binding.model_realization_ref, "model_realization"),
            (binding.runtime_profile_ref, "runtime_profile"),
            (binding.expected_result_schema_ref, "result_schema"),
        )
        for ref, key in exact_refs:
            if ref.artifact_digest != launch[key]["digest"]:
                raise ExternalCodexRuntimeError(
                    "incarnation_artifact_mismatch",
                    f"incarnation {key} ref differs from delivered bytes",
                )
        task_contract_refs = [
            item
            for item in plan.runtime_profile.constraint_refs
            if item.artifact_digest == launch["task"]["digest"]
            and item.schema_version == "abyss_stack_external_codex_task_v1"
        ]
        if (
            len(task_contract_refs) != 1
            or task_contract_refs[0] not in plan.snapshot.source_refs
            or task_contract_refs[0]
            not in binding.continuation.immutable_input_refs
        ):
            raise ExternalCodexRuntimeError(
                "task_contract_unbound",
                "delivered task is not one exact snapshot/continuation-bound runtime constraint",
            )
        if binding.runtime_profile_ref != plan.runtime_profile.provenance:
            raise ExternalCodexRuntimeError(
                "incarnation_runtime_mismatch",
                "incarnation runtime profile differs from the exact plan",
            )
        if (
            task["correlation_id"] != binding.correlation_id
            or task["continuation_id"] != binding.continuation.continuation_id
            or task["expected_incarnation_id"] != binding.incarnation_id
        ):
            raise ExternalCodexRuntimeError(
                "task_identity_mismatch",
                "task correlation, continuation, or incarnation identity differs from the binding",
            )
        if task["target_owner"] not in binding.continuation.owner_scope:
            raise ExternalCodexRuntimeError(
                "task_owner_out_of_scope", "target owner is outside continuation scope"
            )
        if task["return_owner"] != binding.continuation.return_owner.owner_repo:
            raise ExternalCodexRuntimeError(
                "return_owner_mismatch", "task and continuation return owners differ"
            )
        if not set(task["authority_scope"]).issubset(binding.continuation.owner_scope):
            raise ExternalCodexRuntimeError(
                "task_authority_out_of_scope",
                "task authority scope exceeds the continuation owner scope",
            )
        if task["allowed_effect_class"] not in binding.permission_posture.allowed_effect_classes:
            raise ExternalCodexRuntimeError(
                "task_effect_out_of_scope", "task effect exceeds incarnation permission"
            )
        if (
            binding.usage_metering.mode != "observe_only"
            or binding.usage_metering.metering_regime != "chatgpt_quota"
        ):
            raise ExternalCodexRuntimeError(
                "metering_regime_unsupported",
                "ChatGPT execution requires observe-only metering under chatgpt_quota",
            )
        continuation_inputs = set(binding.continuation.immutable_input_refs)
        immutable_inputs: list[dict[str, Any]] = []
        input_ids: set[str] = set()
        input_refs: set[ProvenanceRef] = set()
        for item in task["immutable_inputs"]:
            input_id = str(item["input_id"])
            if INPUT_ID_RE.fullmatch(input_id) is None:
                raise ExternalCodexRuntimeError(
                    "immutable_input_id_invalid",
                    "immutable input ids must be stable lowercase hyphenated identities",
                )
            path = Path(str(item["local_path"]))
            provenance = ProvenanceRef.model_validate(item["provenance"])
            if input_id in input_ids or provenance in input_refs:
                raise ExternalCodexRuntimeError(
                    "immutable_input_duplicate",
                    "task immutable input ids and provenance refs must be unique",
                )
            raw = read_bounded(path)
            if sha256_bytes(raw) != provenance.artifact_digest:
                raise ExternalCodexRuntimeError(
                    "immutable_input_drift",
                    f"immutable input differs from its exact digest: {input_id}",
                )
            if provenance not in continuation_inputs:
                raise ExternalCodexRuntimeError(
                    "immutable_input_out_of_scope",
                    f"immutable input is absent from the continuation: {input_id}",
                )
            input_ids.add(input_id)
            input_refs.add(provenance)
            immutable_inputs.append(
                {
                    "input_id": input_id,
                    "source_path": path,
                    "raw": raw,
                    "provenance": provenance,
                }
            )
        request_inputs = [
            item
            for item in immutable_inputs
            if item["provenance"] == binding.task_request_ref
        ]
        expected_request_input_id = (
            "review-summon-request"
            if task["execution_posture"] == "independent_review"
            else "summon-request"
        )
        if (
            len(request_inputs) != 1
            or request_inputs[0]["input_id"] != expected_request_input_id
        ):
            raise ExternalCodexRuntimeError(
                "incarnation_task_request_unbound",
                "incarnation task request is not the exact canonical immutable summon input",
            )

        owner_admission = None
        if owner_request_path is not None:
            if (
                not owner_request_path.is_absolute()
                or not owner_request_path.is_file()
                or owner_request_path.is_symlink()
            ):
                raise ExternalCodexRuntimeError(
                    "owner_execution_request_unavailable",
                    "owner execution request must be an absolute regular non-symlink file",
                )
            owner_admission = self._validate_owner_contour_admission(
                owner_request_path=owner_request_path,
                launch=launch,
                launch_raw=launch_raw,
                coordinates=coordinates,
                plan=plan,
                binding=binding,
                task=task,
                immutable_inputs=immutable_inputs,
            )

        if (
            realization.get("kind") != "ModelRealization"
            or realization.get("schema_version") != "aoa_model_realization_v1"
            or not isinstance(realization.get("configuration"), dict)
        ):
            raise ExternalCodexRuntimeError(
                "model_realization_invalid", "aoa-models realization identity is invalid"
            )
        configuration = realization["configuration"]
        runtime = configuration.get("runtime")
        tools = configuration.get("tools")
        permissions = configuration.get("permissions")
        access = configuration.get("access")
        if not all(isinstance(item, dict) for item in (runtime, tools, permissions, access)):
            raise ExternalCodexRuntimeError(
                "model_realization_invalid", "model realization configuration is incomplete"
            )
        model_slug = str(runtime.get("model_slug"))
        effort = str(configuration.get("reasoning_effort"))
        model_admission = self.profile["model_admission"]
        if (
            runtime.get("product") != model_admission["runtime_product"]
            or runtime.get("version") != model_admission["runtime_version"]
            or runtime.get("transport") != model_admission["transport"]
            or access.get("auth_regime") != model_admission["auth_regime"]
            or access.get("billing_regime") != model_admission["billing_regime"]
            or realization.get("lifecycle_state")
            not in model_admission["allowed_lifecycle_states"]
        ):
            raise ExternalCodexRuntimeError(
                "model_realization_unsupported", "model realization is not the admitted Codex lane"
            )
        if not model_slug or not effort:
            raise ExternalCodexRuntimeError(
                "model_realization_unsupported",
                "model realization must name a model and reasoning effort",
            )
        tool_entry = next(
            (
                item
                for item in self.profile["tool_profiles"]
                if item["profile_id"] == binding.tool_profile.profile_id
            ),
            None,
        )
        if tool_entry is None:
            raise ExternalCodexRuntimeError(
                "tool_profile_unavailable", "incarnation tool profile is not admitted"
            )
        mcp_configs = tool_entry["mcp_server_configs"]
        if [item["server_id"] for item in mcp_configs] != list(
            binding.tool_profile.required_mcp_server_ids
        ):
            raise ExternalCodexRuntimeError(
                "mcp_profile_mismatch",
                "runtime MCP configs differ from the incarnation MCP profile",
            )
        realization_sandbox_mode = {
            "read_only": "read-only",
            "workspace_write": "workspace-write",
        }.get(str(tool_entry["sandbox_mode"]))
        if (
            tools.get("profile_ref") != binding.tool_profile.profile_id
            or tuple(tools.get("required_tools") or ())
            != binding.tool_profile.required_tool_ids
            or tuple(tools.get("required_mcp_servers") or ())
            != binding.tool_profile.required_mcp_server_ids
            or tools.get("inheritance_allowed") is not False
            or binding.tool_profile.inherit_user_configuration is not False
            or list(binding.permission_posture.allowed_effect_classes)
            != tool_entry["allowed_effect_classes"]
            or binding.permission_posture.sandbox_mode != tool_entry["sandbox_mode"]
            or binding.permission_posture.approval_policy != tool_entry["approval_policy"]
            or binding.permission_posture.network_access != tool_entry["network_access"]
            or binding.permission_posture.external_effects is not False
            or permissions.get("sandbox_mode") != realization_sandbox_mode
            or permissions.get("approval_policy") != tool_entry["approval_policy"]
            or permissions.get("network_access") != tool_entry["network_access"]
            or permissions.get("external_effects") is not False
        ):
            raise ExternalCodexRuntimeError(
                "incarnation_profile_mismatch",
                "model, tool, and permission profiles are not exact",
            )
        if task["execution_posture"] not in self.profile["execution_postures"]:
            raise ExternalCodexRuntimeError(
                "execution_posture_unsupported",
                "execution posture is not runtime-admitted",
            )
        expected_effect = (
            "repo_mutation"
            if binding.permission_posture.sandbox_mode == "workspace_write"
            else "read_only"
        )
        if task["allowed_effect_class"] != expected_effect:
            raise ExternalCodexRuntimeError(
                "task_effect_mismatch", "task effect differs from sandbox posture"
            )
        result_schema = coordinates["result_schema"][2]
        Draft202012Validator.check_schema(result_schema)
        if result_schema != load_schema(REPORT_SCHEMA_PATH):
            raise ExternalCodexRuntimeError(
                "result_schema_mismatch", "launch result schema is not the admitted report schema"
            )

        workspace = Path(str(launch["workspace_path"]))
        if not workspace.is_absolute() or not workspace.is_dir():
            raise ExternalCodexRuntimeError(
                "workspace_unavailable", "workspace path is not an absolute directory"
            )
        if _git_head(workspace) != launch["workspace_expected_head"]:
            raise ExternalCodexRuntimeError(
                "workspace_head_mismatch", "workspace HEAD differs from the launch binding"
            )
        if binding.workspace_source_ref.source_ref != launch["workspace_expected_head"]:
            raise ExternalCodexRuntimeError(
                "workspace_source_mismatch",
                "incarnation workspace source does not name the exact Git HEAD",
            )
        baseline = _git_status(workspace)
        if launch["workspace_initial_posture"] == "clean_required" and baseline:
            raise ExternalCodexRuntimeError(
                "workspace_not_clean", "launch requires a clean isolated workspace"
            )
        workspace_manifest_input_id = str(launch["workspace_manifest_input_id"])
        manifest_inputs = [
            item
            for item in immutable_inputs
            if item["input_id"] == workspace_manifest_input_id
        ]
        if (
            launch["workspace_initial_posture"] == "exact_baseline"
            and len(manifest_inputs) != 1
        ):
            raise ExternalCodexRuntimeError(
                "workspace_manifest_required",
                "exact_baseline requires one immutable workspace-manifest input",
            )
        if len(manifest_inputs) > 1:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_duplicate",
                "workspace baseline may bind only one selected workspace manifest",
            )
        workspace_manifest_baseline: dict[str, Any]
        if manifest_inputs:
            manifest = load_json_bytes(
                manifest_inputs[0]["raw"], label="external Codex workspace manifest"
            )
            assert_workspace_manifest(manifest, workspace)
            workspace_manifest_baseline = manifest
        else:
            workspace_manifest_baseline = build_workspace_manifest(workspace)
        codex_home = Path(str(launch["codex_home"]))
        if not codex_home.is_absolute() or not codex_home.is_dir():
            raise ExternalCodexRuntimeError(
                "codex_home_unavailable", "explicit Codex home is unavailable"
            )
        preflight = self._codex_preflight(launch, model_slug, effort, tool_entry)
        return {
            "launch": launch,
            "launch_raw": launch_raw,
            "launch_digest": sha256_bytes(launch_raw),
            "coordinates": coordinates,
            "plan": plan,
            "binding": binding,
            "task": task,
            "realization": realization,
            "model_slug": model_slug,
            "reasoning_effort": effort,
            "tool_entry": tool_entry,
            "workspace": workspace,
            "baseline": baseline,
            "workspace_manifest_baseline": workspace_manifest_baseline,
            "preflight": preflight,
            "immutable_inputs": immutable_inputs,
            "owner_admission": owner_admission,
        }

    def preflight(
        self,
        launch_path: str | Path,
        *,
        owner_request_path: str | Path | None = None,
    ) -> dict[str, Any]:
        validated = self._validate_launch(
            Path(launch_path),
            owner_request_path=(
                Path(owner_request_path) if owner_request_path is not None else None
            ),
        )
        binding: AgentIncarnationBinding = validated["binding"]
        return {
            "admitted": True,
            "launch_digest": validated["launch_digest"],
            "session_id": validated["launch"]["session_id"],
            "admission_class": validated["launch"]["admission_class"],
            "incarnation_id": binding.incarnation_id,
            "model_slug": validated["model_slug"],
            "reasoning_effort": validated["reasoning_effort"],
            "workspace_head": validated["launch"]["workspace_expected_head"],
            "tool_profile_id": binding.tool_profile.profile_id,
            "external_effects": False,
            "owner_admission_digest": (
                validated["owner_admission"]["request_digest"]
                if validated["owner_admission"] is not None
                else None
            ),
            "preflight": validated["preflight"],
        }

    def start(
        self,
        launch_path: str | Path,
        *,
        owner_request_path: str | Path | None = None,
    ) -> dict[str, Any]:
        validated = self._validate_launch(
            Path(launch_path),
            owner_request_path=(
                Path(owner_request_path) if owner_request_path is not None else None
            ),
        )
        launch = validated["launch"]
        session_id = str(launch["session_id"])
        session_dir = self._session_dir(session_id)
        with self._lock(session_id):
            state_path = self._state_path(session_id)
            if state_path.is_file():
                state = self._load_state(session_id)
                if state.get("launch_digest") != validated["launch_digest"]:
                    raise ExternalCodexRuntimeError(
                        "session_binding_conflict",
                        "session already exists with another launch binding",
                    )
                if (
                    state.get("status") == "prepared"
                    and not state.get("attempts")
                    and state.get("active_attempt_id") is None
                    and state.get("worker_pid") is None
                ):
                    self._spawn_worker(state, mode="start", resume_payload=None)
                return self._public_state(state)
            inputs_dir = session_dir / "inputs"
            materialized: dict[str, str] = {}
            for key, (_, raw, _) in validated["coordinates"].items():
                suffix = ".json"
                target = inputs_dir / f"{key}{suffix}"
                _atomic_write_bytes(target, raw, mode=0o400)
                materialized[key] = str(target)
            if validated["owner_admission"] is not None:
                owner_request_target = inputs_dir / "owner-execution-request.json"
                _atomic_write_bytes(
                    owner_request_target,
                    validated["owner_admission"]["raw"],
                    mode=0o400,
                )
                materialized["owner_execution_request"] = str(owner_request_target)
            execution_result_schema_path = inputs_dir / "execution-result-schema.json"
            execution_result_schema = specialize_report_schema(
                validated["coordinates"]["result_schema"][2],
                task_id=str(validated["task"]["task_id"]),
                incarnation_id=validated["binding"].incarnation_id,
                immutable_input_ids=tuple(
                    str(item["input_id"])
                    for item in validated["immutable_inputs"]
                ),
            )
            _atomic_write_json(
                execution_result_schema_path,
                execution_result_schema,
                mode=0o400,
            )
            _atomic_write_bytes(
                inputs_dir / "launch.json", validated["launch_raw"], mode=0o400
            )
            materialized_task_inputs: list[dict[str, Any]] = []
            for index, item in enumerate(validated["immutable_inputs"], start=1):
                target = inputs_dir / "immutable" / f"{index:03d}.input"
                _atomic_write_bytes(target, item["raw"], mode=0o400)
                materialized_task_inputs.append(
                    {
                        "input_id": item["input_id"],
                        "path": str(target),
                        "provenance": item["provenance"].model_dump(mode="json"),
                    }
                )
            failure_closeout = self._failure_closeout_context(
                binding=validated["binding"],
                task=validated["task"],
                materialized_inputs=materialized,
            )
            state = {
                "schema_version": STATE_SCHEMA_VERSION,
                "session_id": session_id,
                "launch_id": launch["launch_id"],
                "launch_digest": validated["launch_digest"],
                "status": "prepared",
                "admission_class": launch["admission_class"],
                "owner_admission_digest": (
                    validated["owner_admission"]["request_digest"]
                    if validated["owner_admission"] is not None
                    else None
                ),
                "incarnation_id": validated["binding"].incarnation_id,
                "task_id": validated["task"]["task_id"],
                "task_family": validated["task"]["task_family"],
                "execution_posture": validated["task"]["execution_posture"],
                "model_slug": validated["model_slug"],
                "reasoning_effort": validated["reasoning_effort"],
                "tool_profile_id": validated["binding"].tool_profile.profile_id,
                "workspace_path": str(validated["workspace"]),
                "workspace_expected_head": launch["workspace_expected_head"],
                "workspace_baseline": validated["baseline"],
                "workspace_manifest_baseline": validated[
                    "workspace_manifest_baseline"
                ],
                "materialized_inputs": materialized,
                "execution_result_schema_ref": _artifact_ref(
                    execution_result_schema_path,
                    owner="abyss-stack",
                ),
                "materialized_task_inputs": materialized_task_inputs,
                "failure_closeout": failure_closeout,
                "preflight": validated["preflight"],
                "created_at": iso_now(),
                "started_at": None,
                "finished_at": None,
                "thread_id": None,
                "attempts": [],
                "active_attempt_id": None,
                "worker_pid": None,
                "worker_start_ticks": None,
                "supervisor_pid": None,
                "supervisor_start_ticks": None,
                "codex_pid": None,
                "codex_start_ticks": None,
                "last_event_sequence": -1,
                "usage": {
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                },
                "usage_observation_gaps": [],
                "turn_count": 0,
                "output_bytes": 0,
                "active_wall_seconds": 0.0,
                "executed_commands": [],
                "changed_paths": [],
                "result_path": None,
                "result_digest": None,
                "wake_evaluation": None,
            }
            self._append_event(
                state,
                event_type="external_agent.prepared",
                payload={
                    "launch_digest": validated["launch_digest"],
                    "incarnation_id": validated["binding"].incarnation_id,
                },
                significance="progress",
            )
            self._save_state(state)
            self._spawn_worker(state, mode="start", resume_payload=None)
            return self._public_state(state)

    def _spawn_worker(
        self,
        state: dict[str, Any],
        *,
        mode: Literal["start", "resume"],
        resume_payload: Mapping[str, Any] | None,
    ) -> None:
        attempt_number = len(state["attempts"]) + 1
        attempt_id = f"{state['session_id']}:attempt:{attempt_number}"
        session_dir = self._session_dir(str(state["session_id"]))
        attempt_dir = session_dir / "attempts" / f"{attempt_number:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        if resume_payload is not None:
            _atomic_write_json(attempt_dir / "resume.json", resume_payload, mode=0o400)
        read_fd, write_fd = os.pipe()
        try:
            pid = os.fork()
        except BaseException:
            os.close(read_fd)
            os.close(write_fd)
            raise
        if pid == 0:  # pragma: no cover - exercised through subprocess-level tests
            try:
                os.close(write_fd)
                admitted = os.read(read_fd, 1)
                os.close(read_fd)
                if admitted != b"1":
                    os._exit(70)
                os.setsid()
                worker_log = (attempt_dir / "worker.log").open("ab", buffering=0)
                os.dup2(worker_log.fileno(), 1)
                os.dup2(worker_log.fileno(), 2)
                self._run_worker(
                    str(state["session_id"]),
                    attempt_id=attempt_id,
                    attempt_number=attempt_number,
                    mode=mode,
                    resume_payload=resume_payload,
                )
                os._exit(0)
            except BaseException as exc:
                try:
                    with self._lock(str(state["session_id"])):
                        failed_state = self._load_state(str(state["session_id"]))
                        self._worker_failure_locked(
                            failed_state,
                            attempt_id=attempt_id,
                            code=(
                                exc.code
                                if isinstance(exc, ExternalCodexRuntimeError)
                                else "unexpected_worker_failure"
                            ),
                            message=(
                                str(exc)
                                if isinstance(exc, ExternalCodexRuntimeError)
                                else f"worker raised {type(exc).__name__}"
                            ),
                        )
                except BaseException:
                    pass
                os._exit(70)
        os.close(read_fd)
        start_ticks = _process_start_ticks(pid)
        if start_ticks is None:
            os.close(write_fd)
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
            raise ExternalCodexRuntimeError(
                "worker_launch_failed", "cannot identify external-agent worker process"
            )
        attempt = {
            "attempt_id": attempt_id,
            "attempt_number": attempt_number,
            "mode": mode,
            "status": "starting",
            "worker_pid": pid,
            "worker_start_ticks": start_ticks,
            "supervisor_pid": None,
            "supervisor_start_ticks": None,
            "process_identity_ref": None,
            "codex_pid": None,
            "codex_start_ticks": None,
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "thread_id": state.get("thread_id"),
            "codex_argv": None,
            "execution_root": None,
            "output_bytes": 0,
            "active_wall_seconds": 0.0,
            "wall_time_accounted": False,
        }
        try:
            state["attempts"].append(attempt)
            state["active_attempt_id"] = attempt_id
            state["worker_pid"] = pid
            state["worker_start_ticks"] = start_ticks
            state["status"] = "running"
            if state["started_at"] is None:
                state["started_at"] = iso_now()
            # Persist the exact worker identity before the child can leave its
            # one-byte launch gate. A failed save therefore leaves the prior
            # prepared state retryable and emits no misleading start event.
            self._save_state(state)
            self._append_event(
                state,
                event_type=(
                    "external_agent.resume_started"
                    if mode == "resume"
                    else "external_agent.started"
                ),
                payload={"worker_pid": pid, "worker_start_ticks": start_ticks, "mode": mode},
                attempt_id=attempt_id,
                significance="progress",
            )
            self._save_state(state)
            os.write(write_fd, b"1")
        except BaseException:
            os.close(write_fd)
            if _pid_matches(pid, start_ticks):
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
            raise
        else:
            os.close(write_fd)

    def run_to_terminal(
        self,
        launch_path: str | Path,
        *,
        owner_request_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Keep the caller alive until the exact started session is terminal.

        This operation is the lifecycle-compatible entry point for transient
        cgroup launchers whose service ends by terminating all remaining child
        processes.  It adds observation cadence, not an execution deadline or
        resource budget; semantic terminal state remains owned by the runtime.
        """

        state = self.start(
            launch_path,
            owner_request_path=owner_request_path,
        )
        session_id = str(state["session_id"])
        while str(state["status"]) not in TERMINAL_STATES:
            time.sleep(FOREGROUND_OBSERVATION_INTERVAL_SECONDS)
            state = self.status(session_id)
        return state

    def _codex_environment(
        self,
        launch: Mapping[str, Any],
        scratch_root: Path,
        tool_entry: Mapping[str, Any],
    ) -> dict[str, str]:
        environment: dict[str, str] = {}
        for key in launch.get("environment_allowlist", []):
            if SECRET_ENV_RE.search(str(key)):
                continue
            value = os.environ.get(str(key))
            if value is not None:
                environment[str(key)] = value
        environment["CODEX_HOME"] = str(launch["codex_home"])
        environment.setdefault("HOME", os.environ.get("HOME", "/nonexistent"))
        environment.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        environment.setdefault("LANG", "C.UTF-8")
        environment["TMPDIR"] = str(scratch_root)
        environment["NO_COLOR"] = "1"
        for server in tool_entry["mcp_server_configs"]:
            token_name = str(server["bearer_token_env_var"])
            token = os.environ.get(token_name)
            if not token:
                raise ExternalCodexRuntimeError(
                    "mcp_credential_unavailable",
                    f"required role-scoped MCP credential is unavailable: {token_name}",
                )
            environment[token_name] = token
        return environment

    def _materialized_payloads(
        self, state: Mapping[str, Any]
    ) -> tuple[
        dict[str, Any],
        RunPlan,
        AgentIncarnationBinding,
        dict[str, Any],
        dict[str, Any],
        bytes,
    ]:
        inputs = state["materialized_inputs"]
        launch_path = (
            self._session_dir(str(state["session_id"])) / "inputs" / "launch.json"
        )
        launch_raw = read_bounded(launch_path)
        if sha256_bytes(launch_raw) != state["launch_digest"]:
            raise ExternalCodexRuntimeError(
                "materialized_launch_drift", "durable launch bytes changed"
            )
        launch = load_json_bytes(launch_raw, label="materialized launch")
        payloads: dict[str, dict[str, Any]] = {}
        raws: dict[str, bytes] = {}
        for key, path_value in inputs.items():
            raw = read_bounded(
                Path(path_value),
                limit=MAX_ROLE_BYTES if key == "role_contract" else MAX_CONTROL_BYTES,
            )
            expected_digest = (
                state["owner_admission_digest"]
                if key == "owner_execution_request"
                else launch[key]["digest"]
            )
            if sha256_bytes(raw) != expected_digest:
                raise ExternalCodexRuntimeError(
                    "materialized_input_drift",
                    f"durable {key} bytes changed after admission",
                )
            raws[key] = raw
            payloads[key] = load_json_bytes(raw, label=f"materialized {key}")
        if raws["runtime_profile"] != self.profile_raw:
            raise ExternalCodexRuntimeError(
                "materialized_input_drift", "durable runtime profile bytes changed"
            )
        for item in state["materialized_task_inputs"]:
            raw = read_bounded(Path(item["path"]))
            if sha256_bytes(raw) != item["provenance"]["artifact_digest"]:
                raise ExternalCodexRuntimeError(
                    "materialized_input_drift",
                    f"durable immutable input changed: {item['input_id']}",
                )
        plan = RunPlan.model_validate(payloads["plan"])
        binding = AgentIncarnationBinding.model_validate(
            payloads["incarnation_binding"]
        )
        task = payloads["task"]
        realization = payloads["model_realization"]
        assert_agent_incarnation_binding_matches_plan(binding, plan)
        return launch, plan, binding, task, realization, raws["role_contract"]

    def _materialized_task_input(
        self,
        state: Mapping[str, Any],
        input_id: str,
    ) -> tuple[Path, bytes, ProvenanceRef]:
        matches = [
            item
            for item in state["materialized_task_inputs"]
            if item["input_id"] == input_id
        ]
        if len(matches) != 1:
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                f"runtime has no unique immutable {input_id} input",
            )
        item = matches[0]
        path = Path(str(item["path"]))
        immutable_root = (
            self._session_dir(str(state["session_id"]))
            / "inputs"
            / "immutable"
        ).resolve()
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(immutable_root)
        except (OSError, ValueError) as exc:
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                f"immutable {input_id} is absent or outside the session input root",
            ) from exc
        if (
            not path.is_absolute()
            or resolved != path
            or path.is_symlink()
            or not path.is_file()
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                f"immutable {input_id} is not one exact regular session input",
            )
        provenance = ProvenanceRef.model_validate(item["provenance"])
        raw = read_bounded(path)
        if sha256_bytes(raw) != provenance.artifact_digest:
            raise ExternalCodexRuntimeError(
                "materialized_input_drift",
                f"durable immutable input changed: {input_id}",
            )
        return path, raw, provenance

    def _validated_a2a_summon_request(
        self,
        *,
        state: Mapping[str, Any],
        plan: RunPlan,
        binding: AgentIncarnationBinding,
        task: Mapping[str, Any],
        request_input_id: str,
        supplied_path: str | Path | None = None,
    ) -> tuple[dict[str, Any], ProvenanceRef, ProvenanceRef, tuple[str, ...]]:
        """Validate one materialized SDK v4 request and its active plan binding."""

        request_path, request_raw, request_ref = self._materialized_task_input(
            state,
            request_input_id,
        )
        schema_path, schema_raw, schema_ref = self._materialized_task_input(
            state,
            "summon-request-schema",
        )
        if supplied_path is not None:
            supplied = Path(supplied_path)
            if (
                not supplied.is_absolute()
                or supplied.is_symlink()
                or not supplied.is_file()
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_summon_request_unbound",
                    "supplied summon request must be one absolute regular file",
                )
            supplied_raw = read_bounded(supplied)
            if (
                supplied_raw != request_raw
                or sha256_bytes(supplied_raw) != request_ref.artifact_digest
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_summon_request_unbound",
                    "supplied summon request differs from the writer's admitted bytes",
                )
        try:
            request = load_json_bytes(request_raw, label="canonical summon request")
            schema = load_json_bytes(schema_raw, label="canonical summon request schema")
            validate_json(
                request,
                schema_path,
                label="canonical SDK summon request",
            )
        except ExternalCodexRuntimeError as exc:
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_invalid",
                f"canonical SDK summon request/schema is invalid: {exc}",
            ) from exc
        if (
            schema.get("$id") != SDK_SUMMON_REQUEST_SCHEMA_VERSION
            or schema_ref.owner_repo != "aoa-sdk"
            or schema_ref.artifact_ref != SDK_SUMMON_REQUEST_SCHEMA_REF
            or schema_ref.schema_version != SDK_SUMMON_REQUEST_SCHEMA_VERSION
            or request_ref.schema_ref != schema_ref.artifact_ref
            or request_ref.schema_version != SDK_SUMMON_REQUEST_SCHEMA_VERSION
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                "summon request provenance does not bind the exact aoa-sdk v4 schema",
            )
        if (
            not _plan_binds_active_summon_request(plan, request_ref)
            or binding.task_request_ref != request_ref
            or request_ref not in plan.snapshot.source_refs
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                "run plan/incarnation does not bind the exact active summon request",
            )
        nested = request.get("summon_request")
        passport = request.get("quest_passport")
        top_outputs = request.get("expected_outputs")
        if (
            not isinstance(nested, dict)
            or not isinstance(passport, dict)
            or not isinstance(top_outputs, list)
            or not top_outputs
            or any(not isinstance(item, str) or not item for item in top_outputs)
            or len(set(top_outputs)) != len(top_outputs)
            or nested.get("expected_outputs") != top_outputs
            or passport.get("expected_artifacts") != top_outputs
            or passport.get("control_mode") != "codex_supervised"
            or passport.get("self_agent") is not False
            or not isinstance(passport.get("route_anchor"), str)
            or not passport["route_anchor"]
            or nested.get("desired_role") != binding.role_id
            or nested.get("child_agent_id") != binding.incarnation_id
            or nested.get("parent_task_id") != task["parent_task_id"]
            or nested.get("session_ref") != state["session_id"]
            or nested.get("review_required") is not task["review_required"]
            or nested.get("transport_preference") != "codex_local"
            or nested.get("require_progression") is not False
            or nested.get("workspace_root") != state["workspace_path"]
            or request.get("reviewed_artifact_path")
            != nested.get("reviewed_artifact_path")
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                "summon request semantics differ from the exact task/incarnation",
            )
        plan_capabilities = {
            item.capability_id for item in plan.scenario_binding.capability_refs
        }
        request_capabilities = nested.get("capability_refs")
        if (
            not isinstance(request_capabilities, list)
            or not request_capabilities
            or any(item not in plan_capabilities for item in request_capabilities)
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                "summon request capabilities are not bound by the run plan",
            )
        return request, request_ref, schema_ref, tuple(top_outputs)

    def _execution_result_schema_path(self, state: Mapping[str, Any]) -> Path:
        """Return the untampered session-local schema, with legacy fallback."""

        reference = state.get("execution_result_schema_ref")
        if reference is None:
            return Path(str(state["materialized_inputs"]["result_schema"]))
        expected_path = (
            self._session_dir(str(state["session_id"]))
            / "inputs"
            / "execution-result-schema.json"
        )
        candidate = Path(str(reference.get("artifact_ref", "")))
        if (
            candidate != expected_path
            or candidate.is_symlink()
            or not candidate.is_file()
        ):
            raise ExternalCodexRuntimeError(
                "execution_result_schema_drift",
                "session-local result schema is absent or outside runtime inputs",
            )
        raw = read_bounded(candidate)
        if sha256_bytes(raw) != reference.get("artifact_digest"):
            raise ExternalCodexRuntimeError(
                "execution_result_schema_drift",
                "session-local result schema digest drifted",
            )
        actual = load_json_bytes(raw, label="session-local result schema")
        canonical = load_json(
            Path(str(state["materialized_inputs"]["result_schema"])),
            label="materialized canonical result schema",
        )
        expected = specialize_report_schema(
            canonical,
            task_id=str(state["task_id"]),
            incarnation_id=str(state["incarnation_id"]),
            immutable_input_ids=tuple(
                str(item["input_id"])
                for item in state["materialized_task_inputs"]
            ),
        )
        if actual != expected:
            raise ExternalCodexRuntimeError(
                "execution_result_schema_drift",
                "session-local result schema differs from exact runtime identity",
            )
        return candidate

    def _ensure_execution_result_schema_locked(
        self, state: dict[str, Any]
    ) -> Path:
        """Materialize exact identity constraints for a legacy resumable session."""

        if state.get("execution_result_schema_ref") is not None:
            return self._execution_result_schema_path(state)
        canonical = load_json(
            Path(str(state["materialized_inputs"]["result_schema"])),
            label="materialized canonical result schema",
        )
        specialized = specialize_report_schema(
            canonical,
            task_id=str(state["task_id"]),
            incarnation_id=str(state["incarnation_id"]),
            immutable_input_ids=tuple(
                str(item["input_id"])
                for item in state["materialized_task_inputs"]
            ),
        )
        path = (
            self._session_dir(str(state["session_id"]))
            / "inputs"
            / "execution-result-schema.json"
        )
        _atomic_write_json(path, specialized, mode=0o400)
        state["execution_result_schema_ref"] = _artifact_ref(
            path,
            owner="abyss-stack",
        )
        return path

    def _preserved_result_refs(
        self, state: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        """Return exact prior terminal results retained across explicit resume."""

        session_dir = self._session_dir(str(state["session_id"]))
        references: list[dict[str, Any]] = []
        for attempt in state.get("attempts", []):
            attempt_number = attempt.get("attempt_number")
            if not isinstance(attempt_number, int):
                continue
            path = (
                session_dir
                / "attempts"
                / f"{attempt_number:03d}"
                / "runtime-result.json"
            )
            if path.is_file() and not path.is_symlink():
                references.append(_artifact_ref(path))
        return references

    def _owner_admission_ref(
        self, state: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        path_value = state["materialized_inputs"].get("owner_execution_request")
        if path_value is None:
            return None
        path = Path(str(path_value))
        reference = _artifact_ref(path, owner="aoa-agents")
        if reference["artifact_digest"] != state.get("owner_admission_digest"):
            raise ExternalCodexRuntimeError(
                "materialized_input_drift",
                "durable owner execution request changed after admission",
            )
        return reference

    def _attempt_has_completed_usage_event(
        self,
        state: Mapping[str, Any],
        attempt_id: str,
    ) -> bool:
        """Return whether Codex exposed terminal usage for one exact attempt."""

        path = self._events_path(str(state["session_id"]))
        if not path.is_file():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if (
                event.get("attempt_id") == attempt_id
                and event.get("event_type") == "codex.turn.completed"
            ):
                return True
        return False

    def _record_interrupted_usage_gap_locked(
        self,
        state: dict[str, Any],
        attempt_id: str,
    ) -> None:
        """Record that a controlled interrupt precluded exact token observation."""

        gaps = state.setdefault("usage_observation_gaps", [])
        if any(item.get("attempt_id") == attempt_id for item in gaps):
            return
        if self._attempt_has_completed_usage_event(state, attempt_id):
            return
        reason = "controlled_interruption_before_turn_usage"
        event = self._append_event(
            state,
            event_type="external_agent.usage_observation_gap_recorded",
            payload={"attempt_id": attempt_id, "reason": reason},
            attempt_id=attempt_id,
            significance="terminal",
        )
        gaps.append(
            {
                "attempt_id": attempt_id,
                "reason": reason,
                "event_sequence": event["sequence"],
            }
        )

    @staticmethod
    def _usage_observation(state: Mapping[str, Any]) -> dict[str, Any]:
        gaps = [dict(item) for item in state.get("usage_observation_gaps", [])]
        return {
            "status": "partial" if gaps else "complete",
            "gap_reasons": gaps,
        }

    def _render_prompt(
        self,
        *,
        state: Mapping[str, Any],
        binding: AgentIncarnationBinding,
        task: Mapping[str, Any],
        role_raw: bytes,
        execution_root: Path,
        resume_payload: Mapping[str, Any] | None,
    ) -> str:
        role_text = role_raw.decode("utf-8", errors="replace")
        continuation = binding.continuation.model_dump(mode="json")
        immutable_inputs = state["materialized_task_inputs"]
        validation_execution_protocol = [
            {
                "command_id": item["command_id"],
                "task_argv": item["argv"],
                "task_cwd": item["cwd"],
                "execution_argv": list(
                    _validation_wrapper_argv(state["workspace_path"], item)
                ),
            }
            for item in task["validation_commands"]
        ]
        resume_block = (
            "\nResume instruction:\n"
            + json.dumps(resume_payload, ensure_ascii=False, indent=2)
            if resume_payload is not None
            else ""
        )
        workspace_projection = {
            "target_workspace": str(state["workspace_path"]),
            "codex_execution_root": str(execution_root),
            "target_workspace_access": binding.permission_posture.sandbox_mode,
        }
        return f"""You are one external Codex process carrying a bounded AoA role incarnation.

This is not a built-in Codex subagent workflow. Do not delegate, spawn subagents,
or widen the task. The user remains the only human authority. Read the repository
AGENTS.md hierarchy, but treat this exact task packet, permission ceiling, and
continuation obligation as the controlling bounded obligation.

Role source (exact delivered bytes):
<role_contract>
{role_text}
</role_contract>

Task packet:
<task>
{json.dumps(task, ensure_ascii=False, indent=2)}
</task>

Continuation obligation:
<continuation>
{json.dumps(continuation, ensure_ascii=False, indent=2)}
</continuation>

Runtime-materialized immutable inputs (read these paths, not mutable aliases):
<immutable_inputs>
{json.dumps(immutable_inputs, ensure_ascii=False, indent=2)}
</immutable_inputs>

Workspace projection:
<workspace_projection>
{json.dumps(workspace_projection, ensure_ascii=False, indent=2)}
</workspace_projection>

Fixed validation execution protocol:
<validation_execution_protocol>
{json.dumps(validation_execution_protocol, ensure_ascii=False, indent=2)}
</validation_execution_protocol>
{resume_block}

Hard stop-lines:
- Keep the task inside its named workspace and authority scope. For repo-mutation
  work, mutate only allowed_paths; for read-only work, mutate nothing.
- Treat target_workspace above as the only repository under study. The Codex
  process cwd may instead be a runtime-owned attempt-local execution root so
  temporary tools can work without making target_workspace writable. Bind every
  source exploration command explicitly to target_workspace; never cite or
  return execution-root bytes as source evidence or a workspace artifact.
- Anchored source: refs may name only source_evidence_paths. When that optional
  field is absent, allowed_paths is the backward-compatible evidence scope.
- Run every fixed validation through its exact execution_argv above. This
  wrapper binds the task argv to an explicit workspace cwd. A plain argv,
  shell cd, alternate wrapper, or skipped claim is not admitted as execution.
  Report the observed final exit status.
  Each validation_claims evidence_ref must be exactly
  runtime:validation:<command_id>; the runtime binds it to observed argv/status.
- Every transition or finding evidence ref must be an anchored
  source:<workspace-relative-path>#<line-or-symbol>, an anchored
  immutable:<input_id>#<line-or-symbol>, or the reserved post-exit
  runtime:workspace-final-manifest#<line-or-symbol> ref. Use the stable input_id
  shown in immutable_inputs, never its ordinal materialized filename or absolute
  path. A line anchor is spelled exactly L<number> or L<number>-L<number>
  (for example #L35 or #L35-L38). A bare numeric anchor such as #35 is treated
  as a literal symbol, not a line, and fails unless those exact bytes occur in
  the source. Use the reserved runtime ref for claims about final workspace state; the
  controller binds it after the model exits. Emit each exact evidence ref only
  once per transition or finding; exact repetitions are semantically redundant.
- artifact_paths must be empty for read-only work. For repo-mutation work they
  may contain only regular, non-symlink files inside allowed_paths that this
  attempt actually changed relative to the immutable baseline.
- Do not commit, push, create or merge a PR, tag, release, publish, mutate a
  service, inspect secrets, or change global configuration.
- When task.review_required is true, do not return status=completed; preserve
  the independent-review gate with review_required, authority_blocked, or failed.
- A non-review actor that reaches its review gate uses
  review_required/submit_for_review. An independent-review actor uses
  completed/proceed when no blocker remains or
  review_required/return_for_repair when one is confirmed. Any other terminal
  execution failure uses failed/stop; return_for_repair is not a generic retry
  request.
- Do not claim owner acceptance, proof verdict, landing completion, or model fit.
- If owner meaning, architecture, scope, authority, rollback, or safety is
  ambiguous, return authority_blocked or review_required instead of guessing.
- Return one JSON object matching the supplied output schema. Identity fields
  must be task_id={task['task_id']!r} and incarnation_id={binding.incarnation_id!r}.

Runtime session identity: {state['session_id']}
"""

    def _codex_command(
        self,
        *,
        launch: Mapping[str, Any],
        realization: Mapping[str, Any],
        tool_entry: Mapping[str, Any],
        execution_root: Path,
        output_schema: Path,
        output_message: Path,
        mode: Literal["start", "resume"],
        thread_id: str | None,
    ) -> list[str]:
        executable = str(launch["codex_executable"])
        configuration = realization["configuration"]
        model_slug = str(configuration["runtime"]["model_slug"])
        effort = str(configuration["reasoning_effort"])
        base = [
            executable,
            "-a",
            "never",
            "-s",
            str(tool_entry["codex_sandbox"]),
        ]
        execution_root_mode = str(tool_entry["codex_execution_root"])
        base.extend(
            [
                "-C",
                str(execution_root),
                "exec",
            ]
        )
        common = [
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--disable",
            "multi_agent",
            "-m",
            model_slug,
            "-c",
            f'model_reasoning_effort="{effort}"',
            "-c",
            'approval_policy="never"',
            "-c",
            'shell_environment_policy.inherit="core"',
            "-c",
            'shell_environment_policy.exclude=["*KEY*","*TOKEN*","*SECRET*","*PASSWORD*","*CREDENTIAL*"]',
            "--output-schema",
            str(output_schema),
            "--json",
            "-o",
            str(output_message),
        ]
        for server in reversed(tool_entry["mcp_server_configs"]):
            server_id = str(server["server_id"])
            server_config = (
                "{url=\""
                + str(server["url"])
                + "\",bearer_token_env_var=\""
                + str(server["bearer_token_env_var"])
                + "\",enabled=true,required=true}"
            )
            common[0:0] = ["-c", f"mcp_servers.{server_id}={server_config}"]
        if execution_root_mode == "attempt-local":
            common.insert(0, "--skip-git-repo-check")
        if tool_entry["codex_sandbox"] == "workspace-write":
            common[0:0] = [
                "-c",
                "sandbox_workspace_write.network_access=false",
            ]
        if mode == "resume":
            if not thread_id:
                raise ExternalCodexRuntimeError(
                    "resume_thread_missing", "resume requires an exact Codex thread id"
                )
            return [*base, "resume", *common, thread_id, "-"]
        return [*base, *common, "--color", "never", "-"]

    def _run_worker(
        self,
        session_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        mode: Literal["start", "resume"],
        resume_payload: Mapping[str, Any] | None,
    ) -> None:
        session_dir = self._session_dir(session_id)
        attempt_dir = session_dir / "attempts" / f"{attempt_number:03d}"
        scratch = attempt_dir / "scratch"
        execution_root = attempt_dir / "execution-root"
        scratch.mkdir(parents=True, exist_ok=True)
        execution_root.mkdir(parents=True, exist_ok=True)
        with self._lock(session_id):
            state = self._load_state(session_id)
            launch, _, binding, task, realization, role_raw = (
                self._materialized_payloads(state)
            )
            workspace_manifest_input_id = str(
                launch["workspace_manifest_input_id"]
            )
            manifest_inputs = [
                item
                for item in state["materialized_task_inputs"]
                if item["input_id"] == workspace_manifest_input_id
            ]
            if (
                launch["workspace_initial_posture"] == "exact_baseline"
                and len(manifest_inputs) != 1
            ):
                raise ExternalCodexRuntimeError(
                    "workspace_manifest_required",
                    "durable exact_baseline lost its workspace manifest",
                )
            if manifest_inputs:
                manifest = load_json(
                    Path(manifest_inputs[0]["path"]),
                    label="materialized external Codex workspace manifest",
                )
                assert_workspace_manifest(manifest, state["workspace_path"])
            if _git_head(Path(state["workspace_path"])) != state["workspace_expected_head"]:
                self._worker_failure_locked(
                    state,
                    attempt_id=attempt_id,
                    code="workspace_head_drift",
                    message="workspace HEAD changed before Codex launch",
                )
                return
            if _git_status(Path(state["workspace_path"])) != state["workspace_baseline"]:
                self._worker_failure_locked(
                    state,
                    attempt_id=attempt_id,
                    code="workspace_baseline_drift",
                    message="workspace changed between admission and Codex launch",
                )
                return
            tool_entry = next(
                item
                for item in self.profile["tool_profiles"]
                if item["profile_id"] == state["tool_profile_id"]
            )
            self._codex_preflight(
                launch,
                str(state["model_slug"]),
                str(state["reasoning_effort"]),
                tool_entry,
            )
            codex_execution_root = (
                execution_root
                if tool_entry["codex_execution_root"] == "attempt-local"
                else Path(str(state["workspace_path"]))
            )
            target_workspace = Path(str(state["workspace_path"])).resolve()
            resolved_execution_root = codex_execution_root.resolve()
            if (
                tool_entry["codex_execution_root"] == "attempt-local"
                and (
                    resolved_execution_root.is_relative_to(target_workspace)
                    or target_workspace.is_relative_to(resolved_execution_root)
                )
            ):
                self._worker_failure_locked(
                    state,
                    attempt_id=attempt_id,
                    code="execution_root_workspace_overlap",
                    message=(
                        "attempt-local Codex execution root overlaps the target workspace"
                    ),
                )
                return
            prompt = self._render_prompt(
                state=state,
                binding=binding,
                task=task,
                role_raw=role_raw,
                execution_root=codex_execution_root,
                resume_payload=resume_payload,
            )
            prompt_path = attempt_dir / "prompt.txt"
            _atomic_write_bytes(prompt_path, prompt.encode("utf-8"), mode=0o400)
            output_schema = self._execution_result_schema_path(state)
            output_message = attempt_dir / "model-report.json"
            codex_command = self._codex_command(
                launch=launch,
                realization=realization,
                tool_entry=tool_entry,
                execution_root=codex_execution_root,
                output_schema=output_schema,
                output_message=output_message,
                mode=mode,
                thread_id=state.get("thread_id"),
            )
            process_identity_path = attempt_dir / "process-identity.json"
            command = self._containment_command(
                codex_command,
                identity_path=process_identity_path,
            )
            attempt = state["attempts"][attempt_number - 1]
            attempt["status"] = "running"
            attempt["started_at"] = iso_now()
            attempt["codex_argv"] = command
            attempt["execution_root"] = str(codex_execution_root)
            state["status"] = "running"
            self._save_state(state)

        raw_events_path = attempt_dir / "codex-events.jsonl"
        stderr_path = attempt_dir / "codex-stderr.log"
        environment = self._codex_environment(launch, scratch, tool_entry)
        started = utc_now()
        runtime_failure_code: str | None = None
        terminate_requested = False
        interrupt_request_path = attempt_dir / "interrupt-request.json"
        with (
            prompt_path.open("rb") as prompt_handle,
            stderr_path.open("wb") as stderr_handle,
            raw_events_path.open("ab") as raw_handle,
        ):
            process = subprocess.Popen(
                command,
                stdin=prompt_handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                start_new_session=True,
            )
            supervisor_start_ticks = _process_start_ticks(process.pid)
            if supervisor_start_ticks is None:
                process.terminate()
                process.wait(timeout=3)
                raise ExternalCodexRuntimeError(
                    "codex_process_identity_invalid",
                    "cannot record the exact supervisor process identity",
                )
            with self._lock(session_id):
                state = self._load_state(session_id)
                attempt = state["attempts"][attempt_number - 1]
                attempt["supervisor_pid"] = process.pid
                attempt["supervisor_start_ticks"] = supervisor_start_ticks
                state["supervisor_pid"] = process.pid
                state["supervisor_start_ticks"] = supervisor_start_ticks
                self._append_event(
                    state,
                    event_type="external_agent.supervisor_started",
                    payload={
                        "supervisor_pid": process.pid,
                        "supervisor_start_ticks": supervisor_start_ticks,
                    },
                    attempt_id=attempt_id,
                    significance="progress",
                )
                self._save_state(state)
            try:
                process_identity, process_identity_ref = _wait_for_process_identity_receipt(
                    process_identity_path,
                    process=process,
                    supervisor_start_ticks=supervisor_start_ticks,
                )
            except ExternalCodexRuntimeError:
                self._terminate_supervised_process(process, supervisor_start_ticks)
                raise
            codex_pid = int(process_identity["codex_pid"])
            codex_start_ticks = int(process_identity["codex_start_ticks"])
            with self._lock(session_id):
                state = self._load_state(session_id)
                attempt = state["attempts"][attempt_number - 1]
                attempt["supervisor_pid"] = process.pid
                attempt["supervisor_start_ticks"] = supervisor_start_ticks
                attempt["process_identity_ref"] = process_identity_ref
                attempt["codex_pid"] = codex_pid
                attempt["codex_start_ticks"] = codex_start_ticks
                state["supervisor_pid"] = process.pid
                state["supervisor_start_ticks"] = supervisor_start_ticks
                state["codex_pid"] = codex_pid
                state["codex_start_ticks"] = codex_start_ticks
                self._append_event(
                    state,
                    event_type="external_agent.process_started",
                    payload={
                        "supervisor_pid": process.pid,
                        "supervisor_start_ticks": supervisor_start_ticks,
                        "codex_pid": codex_pid,
                        "codex_start_ticks": codex_start_ticks,
                        "process_identity_ref": process_identity_ref,
                        "command_argv_digest": canonical_digest(command),
                    },
                    attempt_id=attempt_id,
                    significance="progress",
                )
                self._save_state(state)
            assert process.stdout is not None and process.stderr is not None
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            stdout_buffer = b""
            while selector.get_map():
                ready = selector.select(timeout=0.25)
                if not ready and process.poll() is not None:
                    ready = [
                        (key, selectors.EVENT_READ) for key in selector.get_map().values()
                    ]
                for key, _ in ready:
                    stream = str(key.data)
                    chunk = os.read(key.fd, 65_536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if stream == "stdout":
                        stdout_buffer += chunk
                        raw_handle.write(chunk)
                        raw_handle.flush()
                    else:
                        stderr_handle.write(chunk)
                        stderr_handle.flush()
                    self._record_output_bytes(
                        session_id,
                        attempt_id=attempt_id,
                        attempt_number=attempt_number,
                        byte_count=len(chunk),
                    )
                    if stream == "stdout":
                        while b"\n" in stdout_buffer:
                            line, stdout_buffer = stdout_buffer.split(b"\n", 1)
                            if len(line) > MAX_EVENT_LINE_BYTES:
                                runtime_failure_code = "codex_event_too_large"
                                terminate_requested = True
                                self._terminate_supervised_process(
                                    process,
                                    supervisor_start_ticks,
                                )
                                break
                            try:
                                self._record_codex_event(
                                    session_id,
                                    attempt_id=attempt_id,
                                    attempt_number=attempt_number,
                                    line=line + b"\n",
                                )
                            except ExternalCodexRuntimeError as exc:
                                runtime_failure_code = exc.code
                                terminate_requested = True
                                self._terminate_supervised_process(
                                    process,
                                    supervisor_start_ticks,
                                )
                                break
                        if (
                            not terminate_requested
                            and len(stdout_buffer) > MAX_EVENT_LINE_BYTES
                        ):
                            runtime_failure_code = "codex_event_too_large"
                            terminate_requested = True
                            self._terminate_supervised_process(
                                process,
                                supervisor_start_ticks,
                            )
                    if terminate_requested:
                        break
                if terminate_requested:
                    break
            selector.close()
            if stdout_buffer and not terminate_requested:
                if len(stdout_buffer) > MAX_EVENT_LINE_BYTES:
                    runtime_failure_code = "codex_event_too_large"
                    terminate_requested = True
                    self._terminate_supervised_process(
                        process,
                        supervisor_start_ticks,
                    )
                else:
                    self._record_codex_event(
                        session_id,
                        attempt_id=attempt_id,
                        attempt_number=attempt_number,
                        line=stdout_buffer,
                    )
            raw_handle.flush()
            stderr_handle.flush()
            os.fsync(raw_handle.fileno())
            os.fsync(stderr_handle.fileno())
            exit_code = process.wait()
        if interrupt_request_path.is_file():
            try:
                interrupt_request = load_json(
                    interrupt_request_path,
                    label="controlled interrupt request",
                )
                if (
                    interrupt_request.get("session_id") != session_id
                    or interrupt_request.get("attempt_id") != attempt_id
                    or interrupt_request.get("supervisor_pid") != process.pid
                    or interrupt_request.get("supervisor_start_ticks")
                    != supervisor_start_ticks
                    or interrupt_request.get("codex_pid") != codex_pid
                    or interrupt_request.get("codex_start_ticks") != codex_start_ticks
                ):
                    raise ExternalCodexRuntimeError(
                        "interrupt_request_invalid",
                        "controlled interrupt request differs from the active process",
                    )
                runtime_failure_code = "controlled_interruption"
            except ExternalCodexRuntimeError as exc:
                runtime_failure_code = exc.code
        finished = utc_now()
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._finalize_attempt_locked(
                state,
                attempt_id=attempt_id,
                attempt_number=attempt_number,
                exit_code=exit_code,
                started=started,
                finished=finished,
                report_path=output_message,
                raw_events_path=raw_events_path,
                stderr_path=stderr_path,
                runtime_failure_code=runtime_failure_code,
            )

    @staticmethod
    def _terminate_supervised_process(
        process: subprocess.Popen[bytes], supervisor_start_ticks: int | None
    ) -> None:
        if supervisor_start_ticks is None:
            raise ExternalCodexRuntimeError(
                "codex_process_identity_invalid",
                "supervisor process start identity was not recorded",
            )
        _terminate_owned_process_group(process.pid, supervisor_start_ticks)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired as exc:
            raise ExternalCodexRuntimeError(
                "codex_process_cleanup_incomplete",
                "supervisor leader did not become waitable after group cleanup",
            ) from exc

    def _record_output_bytes(
        self,
        session_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        byte_count: int,
    ) -> int:
        with self._lock(session_id):
            state = self._load_state(session_id)
            attempt = state["attempts"][attempt_number - 1]
            if attempt["attempt_id"] != attempt_id:
                raise ExternalCodexRuntimeError(
                    "attempt_identity_mismatch", "runtime output belongs to another attempt"
                )
            attempt["output_bytes"] = int(attempt.get("output_bytes", 0)) + byte_count
            state["output_bytes"] = int(state.get("output_bytes", 0)) + byte_count
            self._save_state(state)
            return int(state["output_bytes"])

    def _codex_state_delta(
        self,
        state: Mapping[str, Any],
        *,
        payload: Mapping[str, Any],
        attempt_id: str,
    ) -> dict[str, Any]:
        """Build the exact replayable state delta for one normalized event."""

        if "_runtime_state_delta_v1" in payload:
            raise ExternalCodexRuntimeError(
                "codex_event_reserved_field",
                "Codex event used a runtime-reserved semantic delta field",
            )
        source_type = str(payload.get("type") or "unknown")
        thread_delta: str | None = None
        thread_id = payload.get("thread_id")
        if source_type == "thread.started" and isinstance(thread_id, str) and thread_id:
            thread_delta = thread_id
        usage_delta = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
        }
        turn_increment = 0
        if source_type == "turn.completed" and isinstance(payload.get("usage"), dict):
            turn_increment = 1
            usage = payload["usage"]
            for target in usage_delta:
                value = usage.get(target)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    usage_delta[target] = value
        command_record: dict[str, Any] | None = None
        item = payload.get("item")
        if (
            source_type == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "command_execution"
        ):
            command = _command_text(item)
            command_record = {
                "attempt_id": attempt_id,
                "command": command or "<unavailable>",
                "status": str(item.get("status") or "unknown"),
                "exit_code": item.get("exit_code"),
            }
            if command:
                task = load_json(
                    Path(state["materialized_inputs"]["task"]),
                    label="materialized task",
                )
                wrappers = (
                    _validation_wrapper_argv(state["workspace_path"], spec)
                    for spec in task["validation_commands"]
                )
                if any(
                    _command_matches_argv(command, wrapper)
                    for wrapper in wrappers
                ):
                    command_record["workspace_manifest_digest"] = canonical_digest(
                        build_workspace_manifest(state["workspace_path"])
                    )
        return {
            "thread_id": thread_delta,
            "turn_count_increment": turn_increment,
            "usage_increment": usage_delta,
            "executed_command": command_record,
        }

    def _apply_codex_state_delta(
        self,
        state: dict[str, Any],
        *,
        attempt_id: str,
        source_type: str,
        source_payload: Mapping[str, Any],
        delta: Mapping[str, Any],
    ) -> None:
        """Validate and apply one runtime-authored Codex semantic delta."""

        required = {
            "thread_id",
            "turn_count_increment",
            "usage_increment",
            "executed_command",
        }
        if set(delta) != required:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex event semantic delta has an invalid shape",
            )
        attempt = next(
            (
                item
                for item in state.get("attempts", [])
                if item.get("attempt_id") == attempt_id
            ),
            None,
        )
        if not isinstance(attempt, dict):
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex event semantic delta names no durable attempt",
            )
        expected_thread = (
            source_payload.get("thread_id")
            if source_type == "thread.started"
            and isinstance(source_payload.get("thread_id"), str)
            and source_payload.get("thread_id")
            else None
        )
        if delta.get("thread_id") != expected_thread:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex thread delta differs from the source event",
            )
        if expected_thread is not None:
            previous = state.get("thread_id")
            if previous is not None and previous != expected_thread:
                raise ExternalCodexRuntimeError(
                    "thread_identity_drift",
                    "Codex resume returned another thread identity",
                )
            state["thread_id"] = expected_thread
            attempt["thread_id"] = expected_thread

        expected_turn_increment = int(
            source_type == "turn.completed"
            and isinstance(source_payload.get("usage"), dict)
        )
        if delta.get("turn_count_increment") != expected_turn_increment:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex turn delta differs from the source event",
            )
        usage_delta = delta.get("usage_increment")
        if not isinstance(usage_delta, dict) or set(usage_delta) != {
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
        }:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex usage delta has an invalid shape",
            )
        source_usage = source_payload.get("usage")
        for target in ("input_tokens", "cached_input_tokens", "output_tokens"):
            expected_value = 0
            if expected_turn_increment and isinstance(source_usage, dict):
                raw_value = source_usage.get(target)
                if (
                    isinstance(raw_value, int)
                    and not isinstance(raw_value, bool)
                    and raw_value >= 0
                ):
                    expected_value = raw_value
            if usage_delta.get(target) != expected_value:
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex usage delta differs from the source event",
                )
            state["usage"][target] = int(state["usage"].get(target, 0)) + expected_value
        state["turn_count"] = int(state.get("turn_count", 0)) + expected_turn_increment

        item = source_payload.get("item")
        source_is_command = (
            source_type == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "command_execution"
        )
        command_record = delta.get("executed_command")
        if source_is_command:
            if not isinstance(command_record, dict):
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex command event has no durable execution delta",
                )
            command = _command_text(item)
            expected_record = {
                "attempt_id": attempt_id,
                "command": command or "<unavailable>",
                "status": str(item.get("status") or "unknown"),
                "exit_code": item.get("exit_code"),
            }
            if any(command_record.get(key) != value for key, value in expected_record.items()):
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex command delta differs from the source event",
                )
            if set(command_record) - {*expected_record, "workspace_manifest_digest"}:
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex command delta contains unsupported fields",
                )
            task = load_json(
                Path(state["materialized_inputs"]["task"]),
                label="materialized task",
            )
            is_fixed_validation = bool(command) and any(
                _command_matches_argv(
                    command,
                    _validation_wrapper_argv(state["workspace_path"], spec),
                )
                for spec in task["validation_commands"]
            )
            manifest_digest = command_record.get("workspace_manifest_digest")
            if is_fixed_validation != isinstance(manifest_digest, str) or (
                isinstance(manifest_digest, str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}", manifest_digest) is None
            ):
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex command delta has no exact fixed-validation manifest digest",
                )
            state["executed_commands"].append(dict(command_record))
        elif command_record is not None:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "non-command Codex event carries a command delta",
            )

    def _record_codex_event(
        self,
        session_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        line: bytes,
    ) -> None:
        try:
            payload = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExternalCodexRuntimeError(
                "codex_event_invalid_json",
                "Codex emitted a malformed JSONL protocol record",
            ) from exc
        if not isinstance(payload, dict):
            raise ExternalCodexRuntimeError(
                "codex_event_invalid_shape",
                "Codex emitted a non-object JSONL protocol record",
            )
        source_type = str(payload.get("type") or "unknown")
        with self._lock(session_id):
            state = self._load_state(session_id)
            attempt = state["attempts"][attempt_number - 1]
            if attempt.get("attempt_id") != attempt_id:
                raise ExternalCodexRuntimeError(
                    "attempt_identity_mismatch",
                    "Codex event belongs to another durable attempt",
                )
            delta = self._codex_state_delta(
                state,
                payload=payload,
                attempt_id=attempt_id,
            )
            self._apply_codex_state_delta(
                state,
                attempt_id=attempt_id,
                source_type=source_type,
                source_payload=payload,
                delta=delta,
            )
            normalized_payload = dict(payload)
            normalized_payload["_runtime_state_delta_v1"] = delta
            significance: Literal[
                "trace", "progress", "checkpoint", "review", "authority", "parent_wake", "terminal"
            ] = "progress" if source_type in {"thread.started", "turn.started", "turn.completed"} else "trace"
            self._append_event(
                state,
                event_type=f"codex.{source_type}",
                payload=normalized_payload,
                attempt_id=attempt_id,
                thread_id=state.get("thread_id"),
                source_event_type=source_type,
                significance=significance,
            )
            self._save_state(state)

    def _wake_evaluation(
        self,
        binding: AgentIncarnationBinding,
        status: str,
    ) -> dict[str, Any]:
        event_kind = {
            "completed": "result.validated",
            "review_required": "result.review_required",
            "paused": "result.checkpointed",
            "authority_blocked": "run.authority_required",
            "failed": "result.failed",
            "interrupted": "runtime.interrupted",
        }.get(status, "result.unknown")
        condition = next(
            (
                item
                for item in binding.wake_policy.conditions
                if item.event_kind == event_kind
            ),
            None,
        )
        action = (
            condition.action if condition is not None else binding.wake_policy.default_action
        )
        return {
            "event_kind": event_kind,
            "condition_id": condition.condition_id if condition is not None else None,
            "action": action,
            "wake_parent": action == "wake_parent",
            "reason": (
                condition.description
                if condition is not None
                else "No exact wake condition matched; runtime applied the configured default."
            ),
        }

    def _validate_report_against_task(
        self,
        report: Mapping[str, Any],
        *,
        state: Mapping[str, Any],
        task: Mapping[str, Any],
        binding: AgentIncarnationBinding,
        runtime_evidence_paths: Mapping[str, Path],
        final_workspace_manifest_digest: str | None,
    ) -> None:
        def require_text(value: Any, label: str) -> None:
            if not isinstance(value, str) or not value.strip():
                raise ExternalCodexRuntimeError(
                    "model_report_semantics_invalid",
                    f"model report contains an empty {label}",
                )

        if (
            report.get("task_id") != state["task_id"]
            or report.get("incarnation_id") != state["incarnation_id"]
        ):
            raise ExternalCodexRuntimeError(
                "model_report_identity_mismatch", "model report identity differs from runtime state"
            )
        expected_decision = {
            "completed": "proceed",
            "review_required": (
                "return_for_repair"
                if task["execution_posture"] == "independent_review"
                else "submit_for_review"
            ),
            "authority_blocked": "escalate",
            "failed": "stop",
            "paused": "checkpoint",
        }[str(report["status"])]
        if report.get("decision") != expected_decision:
            raise ExternalCodexRuntimeError(
                "model_report_status_decision_mismatch",
                "model report decision does not match its terminal status",
            )
        require_text(report.get("summary"), "summary")
        transition = report["transition"]
        for key in (
            "from_status",
            "to_status",
            "owner",
            "approval_posture",
            "rollback_reentry_route",
        ):
            require_text(transition.get(key), f"transition {key}")
        transition_evidence = transition["evidence_refs"]
        if not transition_evidence:
            raise ExternalCodexRuntimeError(
                "model_report_semantics_invalid",
                "model report transition evidence refs must be non-empty",
            )
        for value in transition_evidence:
            require_text(value, "transition evidence ref")
            _validate_report_evidence_ref(
                value,
                state=state,
                source_evidence_paths=task.get(
                    "source_evidence_paths", task["allowed_paths"]
                ),
                runtime_evidence_paths=runtime_evidence_paths,
            )
        for finding in report["findings"]:
            require_text(finding.get("category"), "finding category")
            require_text(finding.get("summary"), "finding summary")
            evidence = finding["evidence_refs"]
            if not evidence:
                raise ExternalCodexRuntimeError(
                    "model_report_semantics_invalid",
                    "each finding requires evidence refs",
                )
            for value in evidence:
                require_text(value, "finding evidence ref")
                _validate_report_evidence_ref(
                    value,
                    state=state,
                    source_evidence_paths=task.get(
                        "source_evidence_paths", task["allowed_paths"]
                    ),
                    runtime_evidence_paths=runtime_evidence_paths,
                )
        artifact_paths = report["artifact_paths"]
        if len(artifact_paths) != len(set(artifact_paths)):
            raise ExternalCodexRuntimeError(
                "model_report_semantics_invalid",
                "model report artifact paths must be unique",
            )
        changed_workspace_paths = {
            str(item.get("path")) for item in state["changed_paths"]
        }
        for value in artifact_paths:
            require_text(value, "artifact path")
            if not _relative_path_is_allowed(value, task["allowed_paths"]):
                raise ExternalCodexRuntimeError(
                    "model_report_artifact_out_of_scope",
                    "model report names an artifact outside the allowed workspace paths",
                )
            if task["allowed_effect_class"] == "read_only":
                raise ExternalCodexRuntimeError(
                    "model_report_artifact_forbidden_read_only",
                    "read-only work cannot claim a produced workspace artifact",
                )
            _workspace_artifact_path(state["workspace_path"], value)
            if value not in changed_workspace_paths:
                raise ExternalCodexRuntimeError(
                    "model_report_artifact_not_produced",
                    "model report artifact was not produced relative to the immutable baseline",
                )
        validation_claims = report["validation_claims"]
        expected_command_ids = [
            str(item["command_id"]) for item in task["validation_commands"]
        ]
        actual_command_ids = [str(item.get("command_id")) for item in validation_claims]
        if actual_command_ids != expected_command_ids:
            raise ExternalCodexRuntimeError(
                "model_report_validation_claims_incomplete",
                "model report validation claims must exactly cover fixed task commands in order",
            )
        for command_spec, claim in zip(
            task["validation_commands"], validation_claims, strict=True
        ):
            require_text(claim.get("command_id"), "validation command id")
            require_text(claim.get("evidence_ref"), "validation evidence ref")
            expected_evidence_ref = (
                f"runtime:validation:{command_spec['command_id']}"
            )
            if claim["evidence_ref"] != expected_evidence_ref:
                raise ExternalCodexRuntimeError(
                    "model_report_validation_evidence_unbound",
                    "validation evidence ref differs from its exact command identity",
                )
            executions = [
                item
                for item in state["executed_commands"]
                if item.get("validation_command_id") == command_spec["command_id"]
                and item.get("validation_argv") == command_spec["argv"]
                and item.get("validation_cwd")
                == str(_validation_cwd(state["workspace_path"], command_spec))
                and item.get("validation_wrapper_argv")
                == list(_validation_wrapper_argv(state["workspace_path"], command_spec))
            ]
            if not executions:
                raise ExternalCodexRuntimeError(
                    "model_report_validation_not_executed",
                    "fixed validation command has no exact argv/cwd execution receipt",
                )
            last_execution = executions[-1]
            if (
                not isinstance(final_workspace_manifest_digest, str)
                or last_execution.get("workspace_manifest_digest")
                != final_workspace_manifest_digest
            ):
                raise ExternalCodexRuntimeError(
                    "model_report_validation_workspace_unbound",
                    "fixed validation command was not observed against final workspace bytes",
                )
            observed_status = (
                "passed"
                if last_execution.get("status") == "completed"
                and last_execution.get("exit_code") == 0
                else "failed"
            )
            if claim["status"] != observed_status:
                raise ExternalCodexRuntimeError(
                    "model_report_validation_claim_unbound",
                    "model report validation status differs from the exact observed command",
                )
        for value in report["residuals"]:
            require_text(value, "residual")
        expected = task["transition"]
        if (
            transition["from_status"] != expected["from_status"]
            or transition["owner"] != task["target_owner"]
            or transition["approval_posture"] != expected["approval_posture"]
            or transition["rollback_reentry_route"] != expected["rollback_reentry_route"]
        ):
            raise ExternalCodexRuntimeError(
                "model_report_transition_mismatch",
                "model report changed the exact transition owner or posture",
            )
        if report["status"] in {"completed", "review_required"}:
            expected_to_status = expected["target_status"]
            if (
                report["status"] == "review_required"
                and task["execution_posture"] == "independent_review"
            ):
                expected_to_status = expected["review_required_status"]
            if transition["to_status"] != expected_to_status:
                raise ExternalCodexRuntimeError(
                    "model_report_transition_mismatch",
                    "terminal report does not name its task-owned outcome status",
                )
        if task["review_required"] and report["status"] == "completed":
            raise ExternalCodexRuntimeError(
                "model_report_review_gate_bypassed",
                "task requires independent review before a completed result",
            )
        proposed = report["reentry_request"]
        require_text(proposed.get("condition_id"), "re-entry condition")
        require_text(proposed.get("reason"), "re-entry reason")
        runtime_wake = self._wake_evaluation(binding, str(report["status"]))
        if runtime_wake["condition_id"] is None:
            raise ExternalCodexRuntimeError(
                "model_report_wake_condition_unbound",
                "report status has no exact event-filtered wake condition",
            )
        if proposed["condition_id"] != runtime_wake["condition_id"]:
            raise ExternalCodexRuntimeError(
                "model_report_wake_condition_mismatch",
                "model report wake condition differs from its observed-status binding",
            )
        if proposed["proposed_action"] != runtime_wake["action"]:
            raise ExternalCodexRuntimeError(
                "model_report_wake_action_mismatch",
                "model report proposed an action different from its observed-status binding",
            )

    def _forbidden_effects(
        self,
        commands: Sequence[Mapping[str, Any]],
        task: Mapping[str, Any],
    ) -> list[str]:
        forbidden = set(task["forbidden_effects"])
        detected: set[str] = set()
        for item in commands:
            command = str(item.get("command") or "")
            detected.update(_command_effects(command) & forbidden)
            if (
                item.get("validation_command_id") is None
                and _command_has_unclassified_indirection(command)
            ):
                detected.add("unclassified_indirect_effect")
        return sorted(detected)

    def _failure_authority_effects(
        self,
        commands: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        """Classify an incomplete worker from durable observations alone.

        Failure closeout must remain possible when a materialized launch or
        task is itself the object that drifted. Known effect families are
        intrinsically outside the runtime mandate, while the manifest digest
        recorded with an exact fixed-validation command is its durable
        exemption from the otherwise opaque-interpreter rule.
        """

        detected: set[str] = set()
        for item in commands:
            command = str(item.get("command") or "")
            detected.update(_command_effects(command))
            is_fixed_validation = isinstance(
                item.get("workspace_manifest_digest"), str
            )
            if not is_fixed_validation and _command_has_unclassified_indirection(
                command
            ):
                detected.add("unclassified_indirect_effect")
        return sorted(detected)

    def _finalize_attempt_locked(
        self,
        state: dict[str, Any],
        *,
        attempt_id: str,
        attempt_number: int,
        exit_code: int,
        started: datetime,
        finished: datetime,
        report_path: Path,
        raw_events_path: Path,
        stderr_path: Path,
        runtime_failure_code: str | None,
    ) -> None:
        launch, _, binding, task, _, _ = self._materialized_payloads(state)
        state["executed_commands"] = _annotate_validation_executions(
            state["executed_commands"],
            task=task,
            workspace=state["workspace_path"],
        )
        attempt = state["attempts"][attempt_number - 1]
        attempt["finished_at"] = finished.isoformat().replace("+00:00", "Z")
        attempt["exit_code"] = exit_code
        state["supervisor_pid"] = None
        state["supervisor_start_ticks"] = None
        state["codex_pid"] = None
        state["codex_start_ticks"] = None
        state["worker_pid"] = None
        state["worker_start_ticks"] = None
        state["finished_at"] = finished.isoformat().replace("+00:00", "Z")
        manifest_baseline = state["workspace_manifest_baseline"]
        workspace_manifest_match: bool | None = None
        workspace_manifest_ref: dict[str, Any] | None = None
        final_workspace_manifest_digest: str | None = None
        manifest_observation_gap = False
        head_drift = False
        try:
            current_manifest = build_workspace_manifest(state["workspace_path"])
            final_manifest_path = (
                self._session_dir(str(state["session_id"]))
                / "workspace-final-manifest.json"
            )
            _atomic_write_json(final_manifest_path, current_manifest)
            workspace_manifest_ref = _artifact_ref(final_manifest_path)
            final_workspace_manifest_digest = canonical_digest(current_manifest)
            workspace_manifest_match = current_manifest == manifest_baseline
            changed_paths = compare_workspace_manifest(
                manifest_baseline,
                current_manifest,
            )
            head_drift = (
                manifest_baseline.get("git_head") != current_manifest.get("git_head")
            )
        except ExternalCodexRuntimeError:
            changed_paths = []
            manifest_observation_gap = True
        state["changed_paths"] = changed_paths
        failure_code: str | None = None
        failure_message: str | None = None
        report: dict[str, Any] | None = None
        controlled_interruption = runtime_failure_code == "controlled_interruption"
        if controlled_interruption:
            self._record_interrupted_usage_gap_locked(state, attempt_id)
        if runtime_failure_code is not None:
            failure_code = runtime_failure_code
        if exit_code != 0 and not controlled_interruption:
            failure_code = failure_code or "codex_process_failed"
        if report_path.is_file():
            try:
                report = load_json(report_path, label="model report")
                validate_json(report, REPORT_SCHEMA_PATH, label="model report")
                self._validate_report_against_task(
                    report,
                    state=state,
                    task=task,
                    binding=binding,
                    runtime_evidence_paths=(
                        {"workspace-final-manifest": final_manifest_path}
                        if workspace_manifest_ref is not None
                        else {}
                    ),
                    final_workspace_manifest_digest=final_workspace_manifest_digest,
                )
            except ExternalCodexRuntimeError as exc:
                failure_code = exc.code
                failure_message = str(exc)
                report = None
        elif failure_code is None:
            failure_code = "model_report_missing"

        detected_effects = self._forbidden_effects(state["executed_commands"], task)
        command_observation_gap = any(
            item.get("command") == "<unavailable>"
            for item in state["executed_commands"]
        )
        out_of_scope_paths = [
            item["path"]
            for item in changed_paths
            if not _relative_path_is_allowed(item["path"], task["allowed_paths"])
        ]
        read_only_drift = (
            task["allowed_effect_class"] == "read_only"
            and (
                workspace_manifest_match is False
                or (workspace_manifest_match is None and bool(changed_paths))
            )
        )
        if (
            detected_effects
            or out_of_scope_paths
            or read_only_drift
            or head_drift
            or command_observation_gap
            or manifest_observation_gap
        ):
            status = "authority_blocked"
            failure_code = (
                "command_observation_gap"
                if command_observation_gap
                else "workspace_manifest_observation_gap"
                if manifest_observation_gap
                else failure_code or "authority_boundary_crossed"
            )
        elif controlled_interruption:
            status = "interrupted"
        elif failure_code is not None or report is None:
            status = "failed"
        else:
            status = str(report["status"])
        attempt["status"] = status
        attempt_duration = max(0.0, (finished - started).total_seconds())
        attempt["active_wall_seconds"] = attempt_duration
        attempt["wall_time_accounted"] = True
        state["active_wall_seconds"] = float(
            state.get("active_wall_seconds", 0.0)
        ) + attempt_duration
        state["status"] = status
        wake = self._wake_evaluation(binding, status)
        state["wake_evaluation"] = wake
        validation_payload = {
            "status": status,
            "failure_code": failure_code,
            "detected_forbidden_effects": detected_effects,
            "out_of_scope_paths": out_of_scope_paths,
            "read_only_drift": read_only_drift,
            "workspace_manifest_match": workspace_manifest_match,
            "workspace_head_drift": head_drift,
            "workspace_manifest_observation_gap": manifest_observation_gap,
            "command_observation_gap": command_observation_gap,
        }
        self._append_event(
            state,
            event_type="external_agent.report_validated",
            payload=validation_payload,
            attempt_id=attempt_id,
            significance=(
                "authority"
                if status == "authority_blocked"
                else "checkpoint"
                if status == "paused"
                else "review"
                if status == "review_required"
                else "terminal"
            ),
        )
        self._append_event(
            state,
            event_type="external_agent.wake_evaluated",
            payload=wake,
            attempt_id=attempt_id,
            significance="parent_wake" if wake["wake_parent"] else "terminal",
        )
        events_path = self._events_path(str(state["session_id"]))
        failure_path = self._session_dir(str(state["session_id"])) / "runtime-failure.json"
        if report is None:
            _atomic_write_json(
                failure_path,
                {
                    "schema_version": "abyss_stack_external_codex_failure_v1",
                    "failure_code": failure_code,
                    "message": failure_message,
                    "status": status,
                    "attempt_id": attempt_id,
                },
            )
            report_ref_path = failure_path
        else:
            report_ref_path = report_path
        duration = float(state["active_wall_seconds"])
        usage = {
            **state["usage"],
            "metering_mode": binding.usage_metering.mode,
            "active_cost_regime": "chatgpt_quota",
            "cost_usd": None,
        }
        evidence_refs = [
            _artifact_ref(report_ref_path),
            _artifact_ref(events_path),
            _artifact_ref(stderr_path),
            _artifact_ref(Path(state["materialized_inputs"]["task"]), owner=task["target_owner"]),
            _artifact_ref(Path(state["materialized_inputs"]["incarnation_binding"]), owner="aoa-sdk"),
            _artifact_ref(raw_events_path),
        ]
        if workspace_manifest_ref is not None:
            evidence_refs.append(workspace_manifest_ref)
        owner_admission_ref = self._owner_admission_ref(state)
        if owner_admission_ref is not None:
            evidence_refs.append(owner_admission_ref)
        evidence_refs.extend(self._preserved_result_refs(state))
        result = {
            "schema_version": "abyss_stack_external_codex_result_v1",
            "session_id": state["session_id"],
            "admission_class": state["admission_class"],
            "incarnation_id": state["incarnation_id"],
            "task_id": state["task_id"],
            "task_family": state["task_family"],
            "execution_posture": state["execution_posture"],
            "status": status,
            "failure_code": failure_code,
            "thread_id": state.get("thread_id"),
            "model_slug": state["model_slug"],
            "reasoning_effort": state["reasoning_effort"],
            "started_at": state["started_at"],
            "finished_at": state["finished_at"],
            "duration_seconds": duration,
            "attempt_count": len(state["attempts"]),
            "turn_count": state["turn_count"],
            "output_bytes": state["output_bytes"],
            "active_wall_seconds": state["active_wall_seconds"],
            "exit_code": exit_code,
            "usage": usage,
            "usage_observation": self._usage_observation(state),
            "codex_invocations": self._codex_invocations(state),
            "executed_commands": state["executed_commands"],
            "changed_paths": changed_paths,
            "workspace_manifest_match": workspace_manifest_match,
            "workspace_manifest_ref": workspace_manifest_ref,
            "owner_admission_ref": owner_admission_ref,
            "report_ref": evidence_refs[0],
            "events_ref": evidence_refs[1],
            "stderr_ref": evidence_refs[2],
            "wake_evaluation": wake,
            "evidence_refs": evidence_refs,
        }
        validate_json(result, RESULT_SCHEMA_PATH, label="runtime result")
        result_path = self._session_dir(str(state["session_id"])) / "result.json"
        _atomic_write_json(result_path, result)
        state["result_path"] = str(result_path)
        state["result_digest"] = sha256_file(result_path)
        state["active_attempt_id"] = None
        self._save_state(state)

    def _worker_failure_locked(
        self,
        state: dict[str, Any],
        *,
        attempt_id: str,
        code: str,
        message: str,
    ) -> None:
        cleanup_failed = False
        supervisor_pid, supervisor_ticks = _state_supervisor_identity(state)
        if isinstance(supervisor_pid, int) and isinstance(supervisor_ticks, int):
            try:
                _terminate_owned_process_group(supervisor_pid, supervisor_ticks)
            except ExternalCodexRuntimeError as exc:
                cleanup_failed = True
                code = exc.code
                message = str(exc)
        detected_effects = self._failure_authority_effects(
            state["executed_commands"]
        )
        command_observation_gap = any(
            item.get("command") == "<unavailable>"
            for item in state["executed_commands"]
        )
        authority_crossed = bool(
            cleanup_failed or detected_effects or command_observation_gap
        )
        if command_observation_gap:
            code = "command_observation_gap"
            message = (
                "worker ended after an unobservable command; authority-safe "
                "failure classification is unavailable"
            )
        elif detected_effects:
            code = "authority_boundary_crossed"
            message = (
                "worker ended after a forbidden or unclassified command effect: "
                + ", ".join(detected_effects)
            )
        terminal_status = "authority_blocked" if authority_crossed else "failed"
        self._account_attempt_wall_locked(state, attempt_id, utc_now())
        state["status"] = terminal_status
        state["finished_at"] = iso_now()
        state["worker_pid"] = None
        state["worker_start_ticks"] = None
        if not cleanup_failed:
            state["supervisor_pid"] = None
            state["supervisor_start_ticks"] = None
            state["codex_pid"] = None
            state["codex_start_ticks"] = None
        state["active_attempt_id"] = None
        for attempt in state["attempts"]:
            if attempt["attempt_id"] == attempt_id:
                attempt["status"] = terminal_status
                attempt["finished_at"] = state["finished_at"]
                attempt["exit_code"] = None
        self._append_event(
            state,
            event_type="external_agent.runtime_failed",
            payload={
                "failure_code": code,
                "message": message,
                "detected_forbidden_effects": detected_effects,
                "command_observation_gap": command_observation_gap,
            },
            attempt_id=attempt_id,
            significance="authority" if authority_crossed else "terminal",
        )
        self._write_failure_result_locked(
            state,
            attempt_id=attempt_id,
            code=code,
            message=message,
            status=terminal_status,
        )
        self._save_state(state)

    def _write_failure_result_locked(
        self,
        state: dict[str, Any],
        *,
        attempt_id: str,
        code: str,
        message: str,
        status: str = "failed",
    ) -> None:
        closeout = state.get("failure_closeout")
        if not isinstance(closeout, dict):
            raise ExternalCodexRuntimeError(
                "legacy_failure_closeout_unavailable",
                "legacy runtime state has no admission-time failure closeout envelope",
            )
        session_dir = self._session_dir(str(state["session_id"]))
        failure_path = session_dir / "runtime-failure.json"
        events_path = self._events_path(str(state["session_id"]))
        attempt_number = max(1, len(state["attempts"]))
        worker_log_path = session_dir / "attempts" / f"{attempt_number:03d}" / "worker.log"
        if not worker_log_path.exists():
            _atomic_write_bytes(worker_log_path, b"")
        workspace_manifest_match: bool | None = None
        workspace_manifest_ref: dict[str, Any] | None = None
        try:
            current_manifest = build_workspace_manifest(state["workspace_path"])
            final_manifest_path = session_dir / "workspace-final-manifest.json"
            _atomic_write_json(final_manifest_path, current_manifest)
            workspace_manifest_ref = _artifact_ref(final_manifest_path)
            baseline_manifest = state["workspace_manifest_baseline"]
            changed_paths = compare_workspace_manifest(
                baseline_manifest, current_manifest
            )
            workspace_manifest_match = current_manifest == baseline_manifest
        except ExternalCodexRuntimeError as exc:
            changed_paths = []
            status = "authority_blocked"
            message = (
                f"original failure {code}: {message}; workspace manifest "
                f"observation failed: {exc.code}: {exc}"
            )
            code = "workspace_manifest_observation_gap"
            state["status"] = status
            for attempt in state["attempts"]:
                if attempt["attempt_id"] == attempt_id:
                    attempt["status"] = status
            self._append_event(
                state,
                event_type="external_agent.failure_manifest_unobserved",
                payload={"failure_code": code, "message": message},
                attempt_id=attempt_id,
                significance="authority",
            )
        wake_evaluations = closeout.get("wake_evaluations")
        wake = (
            wake_evaluations.get(status)
            if isinstance(wake_evaluations, dict)
            else None
        )
        if not isinstance(wake, dict):
            raise ExternalCodexRuntimeError(
                "runtime_state_invalid",
                f"failure closeout has no persisted wake evaluation for {status}",
            )
        _atomic_write_json(
            failure_path,
            {
                "schema_version": "abyss_stack_external_codex_failure_v1",
                "failure_code": code,
                "status": status,
                "attempt_id": attempt_id,
                "message": message,
            },
        )
        state["changed_paths"] = changed_paths
        state["wake_evaluation"] = dict(wake)
        evidence_refs = [
            _artifact_ref(failure_path),
            _artifact_ref(events_path),
            _artifact_ref(worker_log_path),
            dict(closeout["task_ref"]),
            dict(closeout["incarnation_binding_ref"]),
        ]
        if workspace_manifest_ref is not None:
            evidence_refs.append(workspace_manifest_ref)
        owner_admission_ref = self._owner_admission_ref(state)
        if owner_admission_ref is not None:
            evidence_refs.append(owner_admission_ref)
        evidence_refs.extend(self._preserved_result_refs(state))
        result = {
            "schema_version": "abyss_stack_external_codex_result_v1",
            "session_id": state["session_id"],
            "admission_class": state["admission_class"],
            "incarnation_id": state["incarnation_id"],
            "task_id": state["task_id"],
            "task_family": state["task_family"],
            "execution_posture": state["execution_posture"],
            "status": status,
            "failure_code": code,
            "thread_id": state.get("thread_id"),
            "model_slug": state["model_slug"],
            "reasoning_effort": state["reasoning_effort"],
            "started_at": state.get("started_at") or state["created_at"],
            "finished_at": state["finished_at"],
            "duration_seconds": float(state.get("active_wall_seconds", 0.0)),
            "attempt_count": len(state["attempts"]),
            "turn_count": int(state.get("turn_count", 0)),
            "output_bytes": int(state.get("output_bytes", 0)),
            "active_wall_seconds": float(state.get("active_wall_seconds", 0.0)),
            "exit_code": None,
            "usage": {
                **state["usage"],
                "metering_mode": "observe_only",
                "active_cost_regime": "chatgpt_quota",
                "cost_usd": None,
            },
            "usage_observation": self._usage_observation(state),
            "codex_invocations": self._codex_invocations(state),
            "executed_commands": state["executed_commands"],
            "changed_paths": changed_paths,
            "workspace_manifest_match": workspace_manifest_match,
            "workspace_manifest_ref": workspace_manifest_ref,
            "owner_admission_ref": owner_admission_ref,
            "report_ref": evidence_refs[0],
            "events_ref": evidence_refs[1],
            "stderr_ref": evidence_refs[2],
            "wake_evaluation": wake,
            "evidence_refs": evidence_refs,
        }
        validate_json(result, RESULT_SCHEMA_PATH, label="runtime failure result")
        result_path = session_dir / "result.json"
        _atomic_write_json(result_path, result)
        state["result_path"] = str(result_path)
        state["result_digest"] = sha256_file(result_path)

    @staticmethod
    def _codex_invocations(state: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "attempt_id": attempt["attempt_id"],
                "mode": attempt["mode"],
                "worker_pid": attempt["worker_pid"],
                "supervisor_pid": attempt.get("supervisor_pid"),
                "supervisor_start_ticks": attempt.get("supervisor_start_ticks"),
                "codex_pid": attempt["codex_pid"],
                "codex_start_ticks": attempt.get("codex_start_ticks"),
                "process_identity_ref": attempt.get("process_identity_ref"),
                "thread_id": attempt["thread_id"],
                "argv": attempt["codex_argv"],
                "argv_digest": canonical_digest(attempt["codex_argv"]),
                "execution_root": attempt.get("execution_root"),
            }
            for attempt in state["attempts"]
            if isinstance(attempt.get("codex_argv"), list)
        ]

    @staticmethod
    def _account_attempt_wall_locked(
        state: dict[str, Any],
        attempt_id: str,
        ended_at: datetime,
    ) -> None:
        for attempt in state["attempts"]:
            if attempt["attempt_id"] != attempt_id:
                continue
            if attempt.get("wall_time_accounted"):
                return
            started_at = attempt.get("started_at")
            active_seconds = (
                max(0.0, (ended_at - parse_timestamp(started_at)).total_seconds())
                if isinstance(started_at, str)
                else 0.0
            )
            attempt["active_wall_seconds"] = active_seconds
            attempt["wall_time_accounted"] = True
            state["active_wall_seconds"] = float(
                state.get("active_wall_seconds", 0.0)
            ) + active_seconds
            return

    def _recover_terminal_result_locked(self, state: dict[str, Any]) -> bool:
        """Commit an atomically written terminal result after a lost state save."""

        session_id = str(state["session_id"])
        result_path = self._session_dir(session_id) / "result.json"
        if not result_path.is_file() or result_path.is_symlink():
            return False
        result = load_json(result_path, label="recoverable runtime result")
        validate_json(result, RESULT_SCHEMA_PATH, label="recoverable runtime result")

        # A resumable session intentionally leaves the preceding result at this
        # path until the next attempt commits. It is evidence, not the current
        # attempt's terminal commit.
        if result.get("attempt_count") != len(state["attempts"]):
            return False

        identity_pairs = (
            ("session_id", session_id),
            ("admission_class", state["admission_class"]),
            ("incarnation_id", state["incarnation_id"]),
            ("task_id", state["task_id"]),
            ("task_family", state["task_family"]),
            ("execution_posture", state["execution_posture"]),
            ("model_slug", state["model_slug"]),
            ("reasoning_effort", state["reasoning_effort"]),
            ("started_at", state["started_at"]),
        )
        if (
            result.get("status") not in {*TERMINAL_STATES, "interrupted"}
            or not isinstance(result.get("finished_at"), str)
            or any(result.get(key) != expected for key, expected in identity_pairs)
        ):
            raise ExternalCodexRuntimeError(
                "runtime_terminal_result_recovery_mismatch",
                "terminal result does not match the active durable session identity",
            )
        if state.get("thread_id") is not None and (
            result.get("thread_id") != state.get("thread_id")
        ):
            raise ExternalCodexRuntimeError(
                "runtime_terminal_result_recovery_mismatch",
                "terminal result changed the durable Codex thread identity",
            )

        expected_events_path = self._events_path(session_id)
        events_ref = result["events_ref"]
        if (
            events_ref not in result["evidence_refs"]
            or events_ref.get("artifact_ref") != str(expected_events_path)
            or events_ref.get("artifact_digest") != state.get("events_digest")
            or _verified_artifact_ref_path(
                events_ref, label="recoverable terminal event stream"
            )
            != expected_events_path
        ):
            raise ExternalCodexRuntimeError(
                "runtime_terminal_result_recovery_mismatch",
                "terminal result does not bind the recovered normalized event stream",
            )
        for key in ("report_ref", "stderr_ref"):
            if result[key] not in result["evidence_refs"]:
                raise ExternalCodexRuntimeError(
                    "runtime_terminal_result_recovery_mismatch",
                    f"terminal result does not bind {key} as evidence",
                )
        for index, evidence_ref in enumerate(result["evidence_refs"]):
            _verified_artifact_ref_path(
                evidence_ref,
                label=f"recoverable terminal evidence {index + 1}",
            )

        attempts_by_id = {
            str(attempt["attempt_id"]): attempt for attempt in state["attempts"]
        }
        for invocation in result["codex_invocations"]:
            attempt = attempts_by_id.get(str(invocation["attempt_id"]))
            if (
                attempt is None
                or invocation["mode"] != attempt["mode"]
                or invocation["worker_pid"] != attempt["worker_pid"]
                or invocation["argv"] != attempt["codex_argv"]
            ):
                raise ExternalCodexRuntimeError(
                    "runtime_terminal_result_recovery_mismatch",
                    "terminal result changed a durable Codex invocation identity",
                )
            attempt["supervisor_pid"] = invocation.get("supervisor_pid")
            attempt["supervisor_start_ticks"] = invocation.get("supervisor_start_ticks")
            attempt["codex_pid"] = invocation.get("codex_pid")
            attempt["codex_start_ticks"] = invocation.get("codex_start_ticks")
            attempt["process_identity_ref"] = invocation.get("process_identity_ref")
            attempt["thread_id"] = invocation.get("thread_id")
            attempt["execution_root"] = invocation.get("execution_root")

        terminal_attempt = state["attempts"][-1]
        prior_attempts = state["attempts"][:-1]
        terminal_attempt["status"] = result["status"]
        terminal_attempt["finished_at"] = result["finished_at"]
        terminal_attempt["exit_code"] = result["exit_code"]
        terminal_attempt["thread_id"] = result["thread_id"]
        terminal_attempt["output_bytes"] = max(
            0,
            int(result["output_bytes"])
            - sum(int(item["output_bytes"]) for item in prior_attempts),
        )
        terminal_attempt["active_wall_seconds"] = max(
            0.0,
            float(result["active_wall_seconds"])
            - sum(float(item["active_wall_seconds"]) for item in prior_attempts),
        )
        terminal_attempt["wall_time_accounted"] = True

        state["status"] = result["status"]
        state["finished_at"] = result["finished_at"]
        state["thread_id"] = result["thread_id"]
        state["usage"] = {
            key: int(result["usage"][key])
            for key in ("input_tokens", "cached_input_tokens", "output_tokens")
        }
        state["usage_observation_gaps"] = [
            dict(item)
            for item in result.get("usage_observation", {}).get("gap_reasons", [])
        ]
        state["turn_count"] = int(result["turn_count"])
        state["output_bytes"] = int(result["output_bytes"])
        state["active_wall_seconds"] = float(result["active_wall_seconds"])
        state["executed_commands"] = list(result["executed_commands"])
        state["changed_paths"] = list(result["changed_paths"])
        state["wake_evaluation"] = dict(result["wake_evaluation"])
        state["result_path"] = str(result_path)
        state["result_digest"] = sha256_file(result_path)
        state["active_attempt_id"] = None
        state["worker_pid"] = None
        state["worker_start_ticks"] = None
        state["supervisor_pid"] = None
        state["supervisor_start_ticks"] = None
        state["codex_pid"] = None
        state["codex_start_ticks"] = None
        self._save_state(state)
        return True

    def _refresh_interrupted_locked(self, state: dict[str, Any]) -> None:
        for attempt in state.get("attempts", []):
            _reap_owned_child(
                attempt.get("worker_pid"),
                attempt.get("worker_start_ticks"),
            )
        if state["status"] != "running":
            return
        if _pid_matches(state.get("worker_pid"), state.get("worker_start_ticks")):
            return
        if self._recover_terminal_result_locked(state):
            return
        attempt_id = str(state.get("active_attempt_id") or "runtime")
        self._append_event(
            state,
            event_type="external_agent.worker_death_observed",
            payload={"reason": "worker process ended without a terminal receipt"},
            attempt_id=attempt_id,
            significance="terminal",
        )
        self._worker_failure_locked(
            state,
            attempt_id=attempt_id,
            code="unexpected_worker_death",
            message=(
                "worker process ended without a terminal receipt; the exact Codex "
                "process group was terminated before failure closeout"
            ),
        )

    def _public_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": state["schema_version"],
            "session_id": state["session_id"],
            "launch_id": state["launch_id"],
            "admission_class": state["admission_class"],
            "status": state["status"],
            "incarnation_id": state["incarnation_id"],
            "task_id": state["task_id"],
            "task_family": state["task_family"],
            "execution_posture": state["execution_posture"],
            "model_slug": state["model_slug"],
            "reasoning_effort": state["reasoning_effort"],
            "thread_id": state.get("thread_id"),
            "attempt_count": len(state["attempts"]),
            "active_attempt_id": state.get("active_attempt_id"),
            "worker_pid": state.get("worker_pid"),
            "supervisor_pid": state.get("supervisor_pid"),
            "codex_pid": state.get("codex_pid"),
            "last_event_sequence": state["last_event_sequence"],
            "created_at": state["created_at"],
            "started_at": state["started_at"],
            "finished_at": state["finished_at"],
            "wake_evaluation": state.get("wake_evaluation"),
            "result_available": bool(state.get("result_path")),
        }

    def status(self, session_id: str) -> dict[str, Any]:
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._refresh_interrupted_locked(state)
            return self._public_state(state)

    def events(self, session_id: str, *, after_sequence: int) -> list[dict[str, Any]]:
        if after_sequence < -1:
            raise ExternalCodexRuntimeError(
                "invalid_event_cursor", "event cursor must be at least -1"
            )
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._refresh_interrupted_locked(state)
            path = self._events_path(session_id)
            events: list[dict[str, Any]] = []
            if path.is_file():
                for _line_number, line in _iter_jsonl_bytes(
                    path,
                    failure_code="runtime_event_state_drift",
                    label="runtime event stream",
                ):
                    item = json.loads(line)
                    if int(item["sequence"]) > after_sequence:
                        events.append(item)
            return events

    def result(self, session_id: str) -> dict[str, Any] | None:
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._refresh_interrupted_locked(state)
            result_path = state.get("result_path")
            if not isinstance(result_path, str):
                return None
            result_file = Path(result_path)
            expected_digest = state.get("result_digest")
            if (
                isinstance(expected_digest, str)
                and sha256_file(result_file) != expected_digest
            ):
                raise ExternalCodexRuntimeError(
                    "runtime_result_drift",
                    "durable runtime result bytes differ from recorded state",
                )
            result = load_json(result_file, label="runtime result")
            validate_json(result, RESULT_SCHEMA_PATH, label="runtime result")
            return result

    def resume(self, session_id: str, resume_path: str | Path) -> dict[str, Any]:
        resume = load_json(Path(resume_path), label="resume request")
        validate_json(resume, RESUME_SCHEMA_PATH, label="resume request")
        with self._lock(session_id):
            state = self._load_state(session_id)
            if state["schema_version"] != STATE_SCHEMA_VERSION:
                raise ExternalCodexRuntimeError(
                    "legacy_session_resume_unsupported",
                    "legacy session lacks the v2 admission-time failure closeout envelope",
                )
            self._refresh_interrupted_locked(state)
            failed_review_followup = state["status"] == "failed"
            if state["status"] not in RESUMABLE_STATES and not failed_review_followup:
                raise ExternalCodexRuntimeError(
                    "resume_state_invalid", f"session is not resumable: {state['status']}"
                )
            if (
                resume["session_id"] != session_id
                or resume["thread_id"] != state.get("thread_id")
                or resume["after_event_sequence"] != state["last_event_sequence"]
            ):
                raise ExternalCodexRuntimeError(
                    "resume_identity_mismatch", "resume request differs from exact durable state"
                )
            if not state.get("thread_id"):
                raise ExternalCodexRuntimeError(
                    "resume_thread_missing", "no durable Codex thread is available"
                )
            task: Mapping[str, Any] | None = None
            if (
                failed_review_followup
                or state.get("execution_result_schema_ref") is None
            ):
                _, _, _, task, _, _ = self._materialized_payloads(state)
                self._ensure_execution_result_schema_locked(state)
            result_path = state.get("result_path")
            result_digest = state.get("result_digest")
            if not isinstance(result_path, str) or not isinstance(result_digest, str):
                raise ExternalCodexRuntimeError(
                    "resume_result_unavailable",
                    "resume requires the exact prior terminal runtime result",
                )
            result_file = Path(result_path)
            raw_result = read_bounded(result_file)
            if sha256_bytes(raw_result) != result_digest:
                raise ExternalCodexRuntimeError(
                    "runtime_result_drift",
                    "prior runtime result bytes differ from recorded state",
                )
            previous_result = load_json_bytes(
                raw_result,
                label="prior runtime result",
            )
            validate_json(
                previous_result,
                RESULT_SCHEMA_PATH,
                label="prior runtime result",
            )
            if (
                previous_result.get("session_id") != session_id
                or previous_result.get("incarnation_id") != state["incarnation_id"]
                or previous_result.get("task_id") != state["task_id"]
                or previous_result.get("status") != state["status"]
            ):
                raise ExternalCodexRuntimeError(
                    "runtime_result_identity_mismatch",
                    "prior runtime result differs from the durable session identity",
                )
            requested_result_digest = resume.get("previous_result_digest")
            if (
                requested_result_digest is not None
                and requested_result_digest != result_digest
            ):
                raise ExternalCodexRuntimeError(
                    "resume_previous_result_mismatch",
                    "resume request names another prior runtime result digest",
                )
            if failed_review_followup:
                if (
                    resume.get("reason") != "review_followup"
                    or resume.get("previous_result_digest") != result_digest
                ):
                    raise ExternalCodexRuntimeError(
                        "failed_review_resume_unbound",
                        "failed review resume must bind the exact prior result digest",
                    )
                if (
                    task is None
                    or task.get("execution_posture") != "independent_review"
                    or task.get("allowed_effect_class") != "read_only"
                    or previous_result.get("failure_code")
                    not in REVIEW_REPORT_RECOVERY_FAILURES
                    or previous_result.get("workspace_manifest_match") is not True
                    or previous_result.get("changed_paths") != []
                ):
                    raise ExternalCodexRuntimeError(
                        "failed_review_resume_unsupported",
                        "only an unchanged read-only review identity failure is recoverable",
                    )
            prior_attempt = state["attempts"][-1]
            preserved_path = (
                self._session_dir(session_id)
                / "attempts"
                / f"{int(prior_attempt['attempt_number']):03d}"
                / "runtime-result.json"
            )
            _atomic_write_bytes(preserved_path, raw_result, mode=0o400)
            preserved_ref = _artifact_ref(preserved_path)
            if preserved_ref["artifact_digest"] != result_digest:
                raise ExternalCodexRuntimeError(
                    "runtime_result_drift",
                    "preserved prior runtime result digest differs",
                )
            if state["status"] == "interrupted":
                self._record_interrupted_usage_gap_locked(
                    state,
                    str(prior_attempt["attempt_id"]),
                )
            self._append_event(
                state,
                event_type="external_agent.resume_source_preserved",
                payload={
                    "previous_status": previous_result["status"],
                    "previous_result_ref": preserved_ref,
                    "reason": resume["reason"],
                },
                attempt_id=str(prior_attempt["attempt_id"]),
                thread_id=str(state["thread_id"]),
                significance=(
                    "review"
                    if state["status"] in {"failed", "review_required"}
                    else "checkpoint"
                ),
            )
            if failed_review_followup:
                self._append_event(
                    state,
                    event_type="external_agent.failed_review_resume_admitted",
                    payload={
                        "failure_code": previous_result["failure_code"],
                        "previous_result_ref": preserved_ref,
                        "reason": resume["reason"],
                    },
                    attempt_id=str(prior_attempt["attempt_id"]),
                    thread_id=str(state["thread_id"]),
                    significance="review",
                )
            state["finished_at"] = None
            state["result_path"] = None
            state["result_digest"] = None
            self._spawn_worker(state, mode="resume", resume_payload=resume)
            return self._public_state(state)

    def interrupt(self, session_id: str) -> dict[str, Any]:
        with self._lock(session_id):
            state = self._load_state(session_id)
            if state["status"] != "running":
                raise ExternalCodexRuntimeError(
                    "interrupt_state_invalid", "only a running session can be interrupted"
                )
            worker_pid = state.get("worker_pid")
            worker_ticks = state.get("worker_start_ticks")
            if not _pid_matches(worker_pid, worker_ticks):
                self._refresh_interrupted_locked(state)
                return self._public_state(state)
            assert isinstance(worker_pid, int)
            if os.getpgid(int(worker_pid)) != int(worker_pid):
                raise ExternalCodexRuntimeError(
                    "worker_identity_invalid", "worker does not own its process group"
                )
            supervisor_pid, supervisor_ticks = _state_supervisor_identity(state)
            if not _pid_matches(supervisor_pid, supervisor_ticks):
                raise ExternalCodexRuntimeError(
                    "interrupt_not_ready",
                    "controlled interruption requires the exact active supervisor",
                )
            assert isinstance(supervisor_pid, int)
            assert isinstance(supervisor_ticks, int)
            if os.getpgid(supervisor_pid) != supervisor_pid:
                raise ExternalCodexRuntimeError(
                    "codex_process_group_invalid",
                    "supervisor does not own the expected descendant process group",
                )
            codex_pid = state.get("codex_pid")
            codex_ticks = state.get("codex_start_ticks")
            if state.get("supervisor_pid") is not None and not _pid_matches(
                codex_pid, codex_ticks
            ):
                raise ExternalCodexRuntimeError(
                    "interrupt_not_ready",
                    "controlled interruption requires the exact active Codex child",
                )
            attempt_id = str(state["active_attempt_id"])
            attempt = next(
                item for item in state["attempts"] if item["attempt_id"] == attempt_id
            )
            attempt_dir = (
                self._session_dir(session_id)
                / "attempts"
                / f"{int(attempt['attempt_number']):03d}"
            )
            _atomic_write_json(
                attempt_dir / "interrupt-request.json",
                {
                    "schema_version": "abyss_stack_external_codex_interrupt_request_v1",
                    "session_id": session_id,
                    "attempt_id": attempt_id,
                    "supervisor_pid": supervisor_pid,
                    "supervisor_start_ticks": supervisor_ticks,
                    "codex_pid": codex_pid,
                    "codex_start_ticks": codex_ticks,
                    "requested_at": iso_now(),
                },
                mode=0o400,
            )
        try:
            os.killpg(supervisor_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with self._lock(session_id):
                state = self._load_state(session_id)
                self._refresh_interrupted_locked(state)
                if state["status"] != "running":
                    return self._public_state(state)
            time.sleep(0.05)
        _terminate_owned_process_group(
            supervisor_pid,
            supervisor_ticks,
            term_timeout=0.0,
            kill_timeout=3.0,
        )
        finalize_deadline = time.monotonic() + 2.0
        while time.monotonic() < finalize_deadline:
            with self._lock(session_id):
                state = self._load_state(session_id)
                self._refresh_interrupted_locked(state)
                if state["status"] != "running":
                    return self._public_state(state)
            time.sleep(0.05)
        if _pid_matches(worker_pid, worker_ticks):
            _terminate_owned_process_group(
                worker_pid,
                worker_ticks,
                term_timeout=2.0,
                kill_timeout=2.0,
            )
        _reap_owned_child(worker_pid, worker_ticks)
        if _pid_matches(worker_pid, worker_ticks):
            raise ExternalCodexRuntimeError(
                "interrupt_incomplete", "worker did not stop after bounded termination"
            )
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._refresh_interrupted_locked(state)
            return self._public_state(state)

    def export_a2a_result(
        self,
        writer_session_id: str,
        *,
        reviewer_session_id: str,
        reviewer_state_root: str | Path | None = None,
        summon_request_path: str | Path,
        output_path: str | Path,
    ) -> dict[str, Any]:
        reviewer_runtime = self
        if reviewer_state_root is not None:
            reviewer_root = Path(reviewer_state_root)
            if (
                not reviewer_root.is_absolute()
                or reviewer_root.is_symlink()
                or not reviewer_root.is_dir()
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_reviewer_state_root_invalid",
                    "reviewer state root must be an existing absolute non-symlink directory",
                )
            if reviewer_root.resolve() != self.state_root.resolve():
                reviewer_runtime = ExternalCodexRuntime(
                    reviewer_root,
                    profile_path=self.profile_path,
                )
        writer = self.result(writer_session_id)
        reviewer = reviewer_runtime.result(reviewer_session_id)
        if writer is None or reviewer is None:
            raise ExternalCodexRuntimeError(
                "a2a_review_incomplete", "writer and reviewer runtime results are required"
            )
        reviewer_receipt_digest = sha256_bytes(
            (
                json.dumps(
                    reviewer,
                    ensure_ascii=True,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")
        )
        if (
            writer.get("admission_class") != "transport_study_fixture"
            or reviewer.get("admission_class") != "transport_study_fixture"
        ):
            raise ExternalCodexRuntimeError(
                "a2a_admission_class_invalid",
                "A2A export accepts only one exact transport-study writer/reviewer pair",
            )
        if (
            reviewer.get("status") not in {"completed", "review_required"}
            or reviewer.get("failure_code") is not None
        ):
            raise ExternalCodexRuntimeError(
                "a2a_review_runtime_failed",
                "failed or authority-blocked reviewer runtime cannot authorize A2A export",
            )
        if (
            writer.get("thread_id") is None
            or reviewer.get("thread_id") is None
            or writer["thread_id"] == reviewer["thread_id"]
            or reviewer.get("execution_posture") != "independent_review"
        ):
            raise ExternalCodexRuntimeError(
                "a2a_review_not_independent", "A2A export requires a separate review thread"
            )
        reviewer_report = _load_verified_json_ref(
            reviewer["report_ref"],
            label="reviewer report",
            schema_path=REPORT_SCHEMA_PATH,
        )
        writer_report = _load_verified_json_ref(
            writer["report_ref"],
            label="writer report",
            schema_path=REPORT_SCHEMA_PATH,
        )
        for label, result, report in (
            ("writer", writer, writer_report),
            ("reviewer", reviewer, reviewer_report),
        ):
            if (
                report.get("task_id") != result.get("task_id")
                or report.get("incarnation_id") != result.get("incarnation_id")
                or report.get("status") != result.get("status")
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_report_identity_mismatch",
                    f"{label} report identity/status differs from its runtime result",
                )
        review_outcomes = {
            ("completed", "proceed"): ("completed", "proceed"),
            ("review_required", "return_for_repair"): (
                "failed",
                "return_for_repair",
            ),
        }
        review_outcome = review_outcomes.get(
            (str(reviewer["status"]), str(reviewer_report["decision"]))
        )
        if review_outcome is None:
            raise ExternalCodexRuntimeError(
                "a2a_review_outcome_invalid",
                "reviewer runtime status and terminal decision are inconsistent",
            )
        with reviewer_runtime._lock(reviewer_session_id):
            reviewer_state = reviewer_runtime._load_state(reviewer_session_id)
            (
                reviewer_launch,
                reviewer_plan,
                reviewer_binding,
                reviewer_task,
                _,
                _,
            ) = reviewer_runtime._materialized_payloads(reviewer_state)
            if (
                reviewer_launch["admission_class"] != "transport_study_fixture"
                or reviewer_state.get("result_path")
                != str(
                    reviewer_runtime._session_dir(reviewer_session_id)
                    / "result.json"
                )
                or reviewer_state.get("result_digest")
                != sha256_file(Path(str(reviewer_state["result_path"])))
                or reviewer_state.get("result_digest")
                != reviewer_receipt_digest
                or reviewer_state.get("incarnation_id")
                != reviewer_binding.incarnation_id
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_review_state_unbound",
                    "reviewer durable state is not bound to its exact result/incarnation",
                )
            (
                reviewer_summon_request,
                reviewer_summon_request_ref,
                reviewer_summon_schema_ref,
                reviewer_expected_outputs,
            ) = reviewer_runtime._validated_a2a_summon_request(
                state=reviewer_state,
                plan=reviewer_plan,
                binding=reviewer_binding,
                task=reviewer_task,
                request_input_id="review-summon-request",
            )
        for label, ref in (
            ("writer events", writer["events_ref"]),
            ("reviewer events", reviewer["events_ref"]),
            ("writer final workspace manifest", writer["workspace_manifest_ref"]),
            (
                "reviewer final workspace manifest",
                reviewer["workspace_manifest_ref"],
            ),
        ):
            if not isinstance(ref, dict):
                raise ExternalCodexRuntimeError(
                    "a2a_artifact_ref_invalid",
                    f"{label} has no exact terminal artifact reference",
                )
            _verified_artifact_ref_path(ref, label=label)
        with self._lock(writer_session_id):
            writer_state = self._load_state(writer_session_id)
            (
                writer_launch,
                writer_plan,
                writer_binding,
                writer_task,
                _,
                _,
            ) = self._materialized_payloads(writer_state)
            writer_result_path = self._session_dir(writer_session_id) / "result.json"
            if (
                writer_launch["admission_class"] != "transport_study_fixture"
                or writer_state.get("result_path") != str(writer_result_path)
                or writer_state.get("result_digest") != sha256_file(writer_result_path)
                or writer_state.get("incarnation_id") != writer_binding.incarnation_id
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_writer_state_unbound",
                    "writer durable state is not bound to its exact result/incarnation",
                )
            (
                summon_request,
                summon_request_ref,
                summon_schema_ref,
                writer_expected_outputs,
            ) = self._validated_a2a_summon_request(
                state=writer_state,
                plan=writer_plan,
                binding=writer_binding,
                task=writer_task,
                request_input_id="summon-request",
                supplied_path=summon_request_path,
            )
            nested = summon_request["summon_request"]
            reviewer_summon_nested = reviewer_summon_request["summon_request"]
            writer_result_digest = str(writer_state["result_digest"])
            writer_report_digest = str(writer["report_ref"]["artifact_digest"])
            reviewer_inputs = {
                str(item["input_id"]): item["provenance"]["artifact_digest"]
                for item in reviewer_task["immutable_inputs"]
            }
            writer_workspace_manifest_digest = str(
                writer["workspace_manifest_ref"]["artifact_digest"]
            )
            if (
                reviewer_inputs.get("writer-runtime-result")
                != writer_result_digest
                or reviewer_inputs.get("writer-model-report")
                != writer_report_digest
                or reviewer_inputs.get("review-workspace-manifest")
                != writer_workspace_manifest_digest
                or reviewer_task["parent_task_id"] != writer["task_id"]
                or reviewer_task["target_owner"] != writer_task["target_owner"]
                or reviewer_state["incarnation_id"] == writer_state["incarnation_id"]
                or nested["parent_task_id"] != writer_task["parent_task_id"]
                or reviewer_summon_nested["parent_task_id"]
                != writer_task["task_id"]
                or reviewer_summon_nested["reviewed_artifact_path"]
                != str(writer_result_path)
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_review_not_bound",
                    "review task/request is not bound to the exact writer result, report, final workspace manifest, owner, and parent",
                )
            returned = ["external_codex_agent_result", "independent_landing_review"]
            returned.extend(str(item) for item in writer_report["artifact_paths"])
            unique_returned = list(dict.fromkeys(returned))
            if (
                not set(writer_expected_outputs).issubset(unique_returned)
                or not set(reviewer_expected_outputs).issubset(unique_returned)
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_return_outputs_incomplete",
                    "returned artifacts do not satisfy the exact writer/reviewer summon requests",
                )
            remote_state, outcome_name = review_outcome
            payload = {
                "reviewed": True,
                "review_status": "reviewed",
                "review_outcome": outcome_name,
                "reviewer_status": reviewer["status"],
                "reviewer_decision": reviewer_report["decision"],
                "reviewed_artifact_path": str(writer_result_path),
                "evidence_digests": {
                    "writer_result": writer_result_digest,
                    "writer_report": writer_report_digest,
                    "reviewer_result": str(reviewer_state["result_digest"]),
                    "reviewer_report": str(reviewer["report_ref"]["artifact_digest"]),
                    "writer_workspace_manifest": str(
                        writer["workspace_manifest_ref"]["artifact_digest"]
                    ),
                    "reviewer_workspace_manifest": str(
                        reviewer["workspace_manifest_ref"]["artifact_digest"]
                    ),
                    "summon_request": summon_request_ref.artifact_digest,
                    "summon_request_schema": summon_schema_ref.artifact_digest,
                    "review_summon_request": (
                        reviewer_summon_request_ref.artifact_digest
                    ),
                    "review_summon_request_schema": (
                        reviewer_summon_schema_ref.artifact_digest
                    ),
                },
                "summon_request_ref": summon_request_ref.model_dump(mode="json"),
                "review_summon_request_ref": (
                    reviewer_summon_request_ref.model_dump(mode="json")
                ),
                "remote_task": {
                    "task_id": writer["task_id"],
                    "state": remote_state,
                    "agent_id": writer_state["incarnation_id"],
                    "endpoint": f"codex://local/{writer['thread_id']}",
                    "returned_artifacts": unique_returned,
                    "context_id": writer["thread_id"],
                    "parent_task_id": nested["parent_task_id"],
                    "artifact_refs": [
                        writer["report_ref"]["artifact_ref"],
                        reviewer["report_ref"]["artifact_ref"],
                        writer["events_ref"]["artifact_ref"],
                        str(writer_result_path),
                    ],
                    "message_refs": [reviewer["events_ref"]["artifact_ref"]],
                },
            }
            output = Path(output_path)
            if not output.is_absolute():
                raise ExternalCodexRuntimeError(
                    "a2a_output_not_absolute", "A2A output path must be absolute"
                )
            if output.is_symlink():
                raise ExternalCodexRuntimeError(
                    "a2a_output_conflict", "A2A output must not be a symbolic link"
                )
            encoded = (
                json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            if output.exists() and read_bounded(output) != encoded:
                raise ExternalCodexRuntimeError(
                    "a2a_output_conflict", "A2A output already contains different bytes"
                )
            _atomic_write_bytes(output, encoded)
            return {
                "child_task_result": payload,
                "artifact_ref": _artifact_ref(output),
                "writer_thread_id": writer["thread_id"],
                "reviewer_thread_id": reviewer["thread_id"],
            }


class ExternalCodexParentReentry:
    """Narrow event-driven Sol yield and exact-thread re-entry bridge.

    This bridge does not schedule work or infer model fit.  It materializes one
    SDK-owned child continuation, lets one external parent Sol turn end, and
    later accepts one immutable child terminal event.  Only the wake policy
    already bound to that child may cause an exact parent-thread resume.
    """

    def __init__(
        self,
        state_root: str | Path,
        *,
        profile_path: str | Path = PROFILE_PATH,
    ) -> None:
        self.state_root = Path(state_root)
        if not self.state_root.is_absolute() or self.state_root.is_symlink():
            raise ExternalCodexRuntimeError(
                "invalid_state_root",
                "external Codex re-entry state root must be absolute and non-symbolic",
            )
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.state_root.is_dir():
            raise ExternalCodexRuntimeError(
                "invalid_state_root", "external Codex re-entry root is not a directory"
            )
        self.profile_path = Path(profile_path)
        self.profile = load_json(self.profile_path, label="runtime profile")
        validate_json(self.profile, PROFILE_SCHEMA_PATH, label="runtime profile")
        validate_structured_output_schema(load_schema(PARENT_YIELD_SCHEMA_PATH))
        validate_structured_output_schema(load_schema(PARENT_REENTRY_SCHEMA_PATH))

    def _reentry_dir(self, reentry_id: str) -> Path:
        return self.state_root / "reentries" / _session_token(reentry_id)

    def _state_path(self, reentry_id: str) -> Path:
        return self._reentry_dir(reentry_id) / "state.json"

    def _events_path(self, reentry_id: str) -> Path:
        return self._reentry_dir(reentry_id) / "events.jsonl"

    @contextmanager
    def _lock(self, reentry_id: str) -> Iterator[None]:
        root = self._reentry_dir(reentry_id)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (root / "reentry.lock").open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _append_event(
        self,
        reentry_id: str,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        significance: str,
    ) -> dict[str, Any]:
        path = self._events_path(reentry_id)
        sequence = 0
        if path.exists():
            raw = read_bounded(path)
            sequence = len([line for line in raw.splitlines() if line.strip()])
        event = {
            "schema_version": "abyss_stack_external_codex_reentry_event_v1",
            "sequence": sequence,
            "observed_at": iso_now(),
            "reentry_id": reentry_id,
            "event_type": event_type,
            "significance": significance,
            "payload": dict(payload),
        }
        _append_jsonl(path, event)
        return event

    def _load_state(self, reentry_id: str) -> dict[str, Any]:
        path = self._state_path(reentry_id)
        if not path.is_file():
            raise ExternalCodexRuntimeError(
                "reentry_not_found", f"parent re-entry is unknown: {reentry_id}"
            )
        state = load_json(path, label="parent re-entry state")
        validate_json(state, REENTRY_STATE_SCHEMA_PATH, label="parent re-entry state")
        if (
            state.get("schema_version") != REENTRY_STATE_SCHEMA_VERSION
            or state.get("reentry_id") != reentry_id
        ):
            raise ExternalCodexRuntimeError(
                "reentry_state_invalid", "parent re-entry state identity differs"
            )
        expected_events_path = self._events_path(reentry_id)
        recorded_events_path = Path(str(state["events_ref"]["artifact_ref"]))
        if recorded_events_path != expected_events_path:
            raise ExternalCodexRuntimeError(
                "reentry_state_invalid",
                "parent re-entry state points outside its canonical event stream",
            )
        try:
            _verified_artifact_ref_path(
                state["events_ref"], label="re-entry event stream"
            )
        except ExternalCodexRuntimeError as exc:
            if exc.code != "a2a_artifact_drift":
                raise
            state = self._recover_appended_events(state)
        return state

    def _recover_appended_events(
        self, state: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Recover a crash between one durable event append and state save.

        Recovery admits only an intact, digest-matching prior JSONL prefix plus
        one or more structurally valid, contiguous events for this re-entry.
        Rewrites, truncation, partial records, or another identity still fail
        closed.
        """

        reentry_id = str(state["reentry_id"])
        path = self._events_path(reentry_id)
        raw = read_bounded(path)
        if not raw.endswith(b"\n"):
            raise ExternalCodexRuntimeError(
                "reentry_event_recovery_failed",
                "re-entry event stream ends with a partial record",
            )
        lines = raw.splitlines(keepends=True)
        recorded_digest = str(state["events_ref"]["artifact_digest"])
        prefix_count: int | None = None
        prefix = b""
        for index, line in enumerate(lines):
            prefix += line
            if sha256_bytes(prefix) == recorded_digest:
                prefix_count = index + 1
        if prefix_count is None or prefix_count >= len(lines):
            raise ExternalCodexRuntimeError(
                "reentry_event_recovery_failed",
                "re-entry event stream is not a strict extension of its recorded prefix",
            )
        events: list[dict[str, Any]] = []
        for sequence, line in enumerate(lines):
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExternalCodexRuntimeError(
                    "reentry_event_recovery_failed",
                    f"re-entry event line {sequence + 1} is invalid",
                ) from exc
            if (
                not isinstance(event, dict)
                or event.get("schema_version")
                != "abyss_stack_external_codex_reentry_event_v1"
                or event.get("sequence") != sequence
                or event.get("reentry_id") != reentry_id
                or not isinstance(event.get("event_type"), str)
                or not event["event_type"]
                or not isinstance(event.get("significance"), str)
                or not event["significance"]
                or not isinstance(event.get("payload"), dict)
            ):
                raise ExternalCodexRuntimeError(
                    "reentry_event_recovery_failed",
                    f"re-entry event line {sequence + 1} is not a contiguous owned event",
                )
            try:
                parse_timestamp(str(event["observed_at"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ExternalCodexRuntimeError(
                    "reentry_event_recovery_failed",
                    f"re-entry event line {sequence + 1} has no valid observation time",
                ) from exc
            events.append(event)
        recovered = dict(state)
        for event in events[prefix_count:]:
            payload = event["payload"]
            event_type = event["event_type"]
            if event_type == "external_parent.child_event_admitted":
                child_result_ref = payload.get("child_result_ref")
                wake_evaluation = payload.get("wake_evaluation")
                if not isinstance(child_result_ref, dict) or not isinstance(
                    wake_evaluation, dict
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_event_recovery_failed",
                        "admitted child event lacks its semantic state delta",
                    )
                _verified_artifact_ref_path(
                    child_result_ref, label="recovered child result"
                )
                recovered["child_result_ref"] = child_result_ref
                recovered["wake_evaluation"] = wake_evaluation
            elif event_type == "external_parent.wake_filtered":
                recovered["status"] = "filtered"
            elif event_type == "external_parent.reentry_failed":
                recovered["status"] = "failed"
            elif event_type == "external_parent.reentry_completed":
                turn = payload.get("turn")
                result_ref = payload.get("reentry_result_ref")
                if (
                    not isinstance(turn, dict)
                    or turn.get("kind") != "reentry"
                    or turn.get("thread_id") != recovered["parent_thread_id"]
                    or not isinstance(result_ref, dict)
                    or turn.get("output_ref") != result_ref
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_event_recovery_failed",
                        "completed re-entry event lacks its semantic state delta",
                    )
                _verified_artifact_ref_path(
                    result_ref, label="recovered parent re-entry result"
                )
                recovered["turns"] = [recovered["turns"][0], turn]
                recovered["reentry_result_ref"] = result_ref
                recovered["status"] = "reentered"
        recovered["updated_at"] = iso_now()
        recovered["events_ref"] = _artifact_ref(path)
        validate_json(
            recovered, REENTRY_STATE_SCHEMA_PATH, label="recovered parent re-entry state"
        )
        _atomic_write_json(self._state_path(reentry_id), recovered, mode=0o600)
        return recovered

    def _save_state(self, state: Mapping[str, Any]) -> None:
        candidate = dict(state)
        candidate["updated_at"] = iso_now()
        candidate["events_ref"] = _artifact_ref(
            self._events_path(str(candidate["reentry_id"]))
        )
        validate_json(candidate, REENTRY_STATE_SCHEMA_PATH, label="parent re-entry state")
        _atomic_write_json(
            self._state_path(str(candidate["reentry_id"])), candidate, mode=0o600
        )

    @staticmethod
    def _artifact_copy(
        ref: Mapping[str, Any],
        *,
        label: str,
        destination: Path,
    ) -> dict[str, Any]:
        source = _verified_artifact_ref_path(ref, label=label)
        _atomic_write_bytes(destination, read_bounded(source), mode=0o400)
        copied = dict(ref)
        copied["artifact_ref"] = str(destination)
        if sha256_file(destination) != copied["artifact_digest"]:
            raise ExternalCodexRuntimeError(
                "reentry_input_copy_failed", f"materialized {label} digest differs"
            )
        return copied

    def _materialize_obligation(
        self, obligation_path: Path, obligation: Mapping[str, Any]
    ) -> tuple[Path, dict[str, Any]]:
        root = self._reentry_dir(str(obligation["reentry_id"])) / "inputs"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        materialized = dict(obligation)
        for key, name in (
            ("parent_model_realization_ref", "parent-model-realization.json"),
            ("parent_role_ref", "parent-role.json"),
            ("child_task_ref", "child-task.json"),
            ("child_incarnation_binding_ref", "child-incarnation-binding.json"),
        ):
            materialized[key] = self._artifact_copy(
                obligation[key], label=key, destination=root / name
            )
        materialized_path = root / "obligation.json"
        _atomic_write_json(materialized_path, materialized, mode=0o400)
        validate_json(
            materialized,
            PARENT_OBLIGATION_SCHEMA_PATH,
            label="materialized parent obligation",
        )
        return materialized_path, materialized

    def _validate_obligation(
        self, obligation: Mapping[str, Any]
    ) -> tuple[dict[str, Any], AgentIncarnationBinding, dict[str, Any]]:
        task = _load_verified_json_ref(
            obligation["child_task_ref"],
            label="child task",
            schema_path=TASK_SCHEMA_PATH,
        )
        binding_raw = _load_verified_json_ref(
            obligation["child_incarnation_binding_ref"],
            label="child incarnation binding",
        )
        try:
            binding = AgentIncarnationBinding.model_validate(binding_raw)
        except Exception as exc:
            raise ExternalCodexRuntimeError(
                "reentry_binding_invalid", "child incarnation binding is invalid"
            ) from exc
        realization = _load_verified_json_ref(
            obligation["parent_model_realization_ref"],
            label="parent model realization",
        )
        _verified_artifact_ref_path(obligation["parent_role_ref"], label="parent role")

        if (
            task["parent_task_id"] != obligation["parent_task_id"]
            or task["expected_incarnation_id"] != binding.incarnation_id
            or task["continuation_id"] != binding.continuation.continuation_id
            or task["return_owner"] != obligation["return_owner"]
            or binding.continuation.return_owner.owner_repo
            != obligation["return_owner"]
            or tuple(obligation["deferred_parent_decisions"])
            != binding.continuation.deferred_parent_decisions
        ):
            raise ExternalCodexRuntimeError(
                "reentry_identity_mismatch",
                "parent obligation, child task, binding, or return owner differs",
            )
        matching = [
            condition
            for condition in binding.wake_policy.conditions
            if condition.condition_id == obligation["expected_wake_condition_id"]
        ]
        if (
            len(matching) != 1
            or matching[0].event_kind != obligation["expected_wake_event_kind"]
            or matching[0].action != "wake_parent"
            or matching[0].condition_id
            not in binding.wake_policy.escalation_conditions
        ):
            raise ExternalCodexRuntimeError(
                "reentry_wake_unbound",
                "expected wake is not one exact escalation condition in the binding",
            )

        configuration = realization.get("configuration")
        runtime = configuration.get("runtime") if isinstance(configuration, dict) else None
        permissions = (
            configuration.get("permissions") if isinstance(configuration, dict) else None
        )
        if (
            realization.get("kind") != "ModelRealization"
            or not isinstance(runtime, dict)
            or runtime.get("model_slug") != "gpt-5.6-sol"
            or runtime.get("transport") != "exec-jsonl"
            or configuration.get("reasoning_effort") != "max"
            or not isinstance(permissions, dict)
            or permissions.get("sandbox_mode") != "read-only"
            or permissions.get("approval_policy") != "never"
            or permissions.get("external_effects") is not False
        ):
            raise ExternalCodexRuntimeError(
                "reentry_parent_realization_invalid",
                "parent realization is not exact read-only Sol max exec-jsonl",
            )

        executable = Path(str(obligation["codex_executable"]))
        workspace = Path(str(obligation["parent_workspace"]))
        codex_home = Path(str(obligation["codex_home"]))
        if (
            not executable.is_file()
            or executable.is_symlink()
            or sha256_file(executable) != obligation["codex_executable_digest"]
        ):
            raise ExternalCodexRuntimeError(
                "reentry_codex_drift", "parent Codex executable identity differs"
            )
        if (
            not workspace.is_dir()
            or workspace.is_symlink()
            or not codex_home.is_dir()
            or codex_home.is_symlink()
        ):
            raise ExternalCodexRuntimeError(
                "reentry_runtime_coordinate_invalid",
                "parent workspace or Codex home is unavailable or symbolic",
            )
        return task, binding, realization

    @staticmethod
    def _codex_usage(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
        completed = [event for event in events if event.get("type") == "turn.completed"]
        if len(completed) != 1 or not isinstance(completed[0].get("usage"), dict):
            raise ExternalCodexRuntimeError(
                "reentry_turn_incomplete", "parent turn has no exact completion usage"
            )
        usage = completed[0]["usage"]
        values: dict[str, int] = {}
        for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
            value = usage.get(key, 0)
            if not isinstance(value, int) or value < 0:
                raise ExternalCodexRuntimeError(
                    "reentry_usage_invalid", f"parent turn {key} is invalid"
                )
            values[key] = value
        return values

    def _codex_environment(self, obligation: Mapping[str, Any], scratch: Path) -> dict[str, str]:
        environment = {
            "CODEX_HOME": str(obligation["codex_home"]),
            "HOME": os.environ.get("HOME", "/nonexistent"),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "TMPDIR": str(scratch),
            "NO_COLOR": "1",
        }
        return environment

    def _codex_command(
        self,
        obligation: Mapping[str, Any],
        realization: Mapping[str, Any],
        *,
        output_schema: Path,
        output_message: Path,
        thread_id: str | None,
    ) -> list[str]:
        configuration = realization["configuration"]
        common = [
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--disable",
            "multi_agent",
            "-m",
            str(configuration["runtime"]["model_slug"]),
            "-c",
            f'model_reasoning_effort="{configuration["reasoning_effort"]}"',
            "-c",
            'approval_policy="never"',
            "-c",
            'shell_environment_policy.inherit="core"',
            "-c",
            'shell_environment_policy.exclude=["*KEY*","*TOKEN*","*SECRET*","*PASSWORD*","*CREDENTIAL*"]',
            "--output-schema",
            str(output_schema),
            "--json",
            "-o",
            str(output_message),
        ]
        base = [
            str(obligation["codex_executable"]),
            "-a",
            "never",
            "-s",
            "read-only",
            "-C",
            str(obligation["parent_workspace"]),
            "exec",
        ]
        if thread_id is None:
            return [*base, *common, "--color", "never", "-"]
        return [*base, "resume", *common, thread_id, "-"]

    def _containment_command(self, command: Sequence[str], identity_path: Path) -> list[str]:
        containment = self.profile["process_containment"]
        return [
            sys.executable,
            str(SUPERVISOR_PATH),
            "--parent-pid",
            str(os.getpid()),
            "--term-timeout-seconds",
            str(containment["term_timeout_seconds"]),
            "--kill-timeout-seconds",
            str(containment["kill_timeout_seconds"]),
            "--identity-file",
            str(identity_path),
            "--",
            *command,
        ]

    def _run_parent_turn(
        self,
        obligation: Mapping[str, Any],
        realization: Mapping[str, Any],
        *,
        kind: Literal["yield", "reentry"],
        prompt: str,
        thread_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        reentry_id = str(obligation["reentry_id"])
        index = 1 if kind == "yield" else 2
        turn_root = self._reentry_dir(reentry_id) / "turns" / f"{index:03d}-{kind}"
        if turn_root.exists():
            raise ExternalCodexRuntimeError(
                "reentry_turn_already_materialized",
                f"parent {kind} turn already has durable bytes",
            )
        scratch = turn_root / "scratch"
        scratch.mkdir(parents=True, exist_ok=False, mode=0o700)
        prompt_path = turn_root / "prompt.txt"
        events_path = turn_root / "codex-events.jsonl"
        stderr_path = turn_root / "codex-stderr.log"
        output_path = turn_root / "model-output.json"
        identity_path = turn_root / "process-identity.json"
        _atomic_write_bytes(prompt_path, prompt.encode("utf-8"), mode=0o400)
        output_schema = (
            PARENT_YIELD_SCHEMA_PATH if kind == "yield" else PARENT_REENTRY_SCHEMA_PATH
        )
        command = self._containment_command(
            self._codex_command(
                obligation,
                realization,
                output_schema=output_schema,
                output_message=output_path,
                thread_id=thread_id,
            ),
            identity_path,
        )
        started_at = iso_now()
        with (
            prompt_path.open("rb") as prompt_handle,
            events_path.open("wb") as events_handle,
            stderr_path.open("wb") as stderr_handle,
        ):
            process = subprocess.Popen(
                command,
                stdin=prompt_handle,
                stdout=events_handle,
                stderr=stderr_handle,
                env=self._codex_environment(obligation, scratch),
                start_new_session=True,
            )
            try:
                exit_code = process.wait()
            except BaseException:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise
        finished_at = iso_now()
        raw_events = read_bounded(events_path)
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw_events.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExternalCodexRuntimeError(
                    "reentry_codex_protocol_invalid",
                    f"parent turn JSONL line {line_number} is invalid",
                ) from exc
            if not isinstance(record, dict):
                raise ExternalCodexRuntimeError(
                    "reentry_codex_protocol_invalid",
                    f"parent turn JSONL line {line_number} is not an object",
                )
            records.append(record)
        thread_ids = {
            str(record["thread_id"])
            for record in records
            if record.get("type") == "thread.started"
            and isinstance(record.get("thread_id"), str)
        }
        if exit_code != 0 or len(thread_ids) != 1 or not output_path.is_file():
            raise ExternalCodexRuntimeError(
                "reentry_parent_turn_failed",
                f"parent {kind} turn failed before a unique structured result",
            )
        observed_thread = next(iter(thread_ids))
        if thread_id is not None and observed_thread != thread_id:
            raise ExternalCodexRuntimeError(
                "reentry_parent_thread_drift",
                "parent resume returned another thread identity",
            )
        output = load_json(output_path, label=f"parent {kind} output")
        validate_json(output, output_schema, label=f"parent {kind} output")
        turn = {
            "kind": kind,
            "started_at": started_at,
            "finished_at": finished_at,
            "exit_code": exit_code,
            "thread_id": observed_thread,
            "events_ref": _artifact_ref(events_path),
            "output_ref": _artifact_ref(output_path),
            "usage": self._codex_usage(records),
        }
        return turn, output

    @staticmethod
    def _yield_prompt(
        obligation: Mapping[str, Any],
        task: Mapping[str, Any],
        binding: AgentIncarnationBinding,
    ) -> str:
        payload = {
            "reentry_id": obligation["reentry_id"],
            "parent_task_id": obligation["parent_task_id"],
            "return_owner": obligation["return_owner"],
            "expected_wake": {
                "condition_id": obligation["expected_wake_condition_id"],
                "event_kind": obligation["expected_wake_event_kind"],
                "action": "wake_parent",
            },
            "deferred_parent_decisions": obligation["deferred_parent_decisions"],
            "child_task": task,
            "continuation": binding.continuation.model_dump(mode="json"),
        }
        return (
            "Ты — отдельный parent Sol max в контролируемом L2 yield. Не используй "
            "инструменты, не меняй файлы и не запускай дочерние процессы. Проверь "
            "согласованность уже типизированной child obligation ниже. Если identity, "
            "owner, invariants, done-state и wake condition согласованы, заверши inference "
            "и верни JSON decision=yield. Скопируй reentry_id, continuation_id, "
            "child task_id, expected event kind и deferred_parent_decisions дословно. "
            "Ничего не принимай за human authority.\n\n"
            + "<parent_payload>\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n</parent_payload>"
        )

    @staticmethod
    def _validate_yield_output(
        output: Mapping[str, Any],
        obligation: Mapping[str, Any],
        task: Mapping[str, Any],
        binding: AgentIncarnationBinding,
    ) -> None:
        if (
            output["reentry_id"] != obligation["reentry_id"]
            or output["continuation_id"] != binding.continuation.continuation_id
            or output["child_task_id"] != task["task_id"]
            or output["expected_event_kind"] != obligation["expected_wake_event_kind"]
            or output["deferred_parent_decisions"]
            != obligation["deferred_parent_decisions"]
            or not str(output["summary"]).strip()
        ):
            raise ExternalCodexRuntimeError(
                "reentry_parent_yield_mismatch",
                "parent yield output differs from the immutable continuation",
            )

    def yield_parent(self, obligation_path: str | Path) -> dict[str, Any]:
        path = Path(obligation_path)
        obligation = load_json(path, label="parent re-entry obligation")
        validate_json(
            obligation,
            PARENT_OBLIGATION_SCHEMA_PATH,
            label="parent re-entry obligation",
        )
        reentry_id = str(obligation["reentry_id"])
        with self._lock(reentry_id):
            if self._state_path(reentry_id).exists():
                raise ExternalCodexRuntimeError(
                    "reentry_already_exists", "parent re-entry state already exists"
                )
            self._validate_obligation(obligation)
            materialized_path, materialized = self._materialize_obligation(path, obligation)
            task, binding, realization = self._validate_obligation(materialized)
            turn, output = self._run_parent_turn(
                materialized,
                realization,
                kind="yield",
                prompt=self._yield_prompt(materialized, task, binding),
                thread_id=None,
            )
            self._validate_yield_output(output, materialized, task, binding)
            self._append_event(
                reentry_id,
                event_type="external_parent.inference_yielded",
                payload={
                    "thread_id": turn["thread_id"],
                    "turn_output_digest": turn["output_ref"]["artifact_digest"],
                },
                significance="checkpoint",
            )
            self._append_event(
                reentry_id,
                event_type="external_parent.wait_registered",
                payload={
                    "condition_id": materialized["expected_wake_condition_id"],
                    "event_kind": materialized["expected_wake_event_kind"],
                    "child_task_id": task["task_id"],
                    "child_incarnation_id": binding.incarnation_id,
                },
                significance="waiting",
            )
            now = iso_now()
            state = {
                "schema_version": REENTRY_STATE_SCHEMA_VERSION,
                "reentry_id": reentry_id,
                "status": "waiting",
                "created_at": now,
                "updated_at": now,
                "obligation_ref": _artifact_ref(materialized_path),
                "parent_thread_id": turn["thread_id"],
                "continuation_id": binding.continuation.continuation_id,
                "child_task_id": task["task_id"],
                "child_incarnation_id": binding.incarnation_id,
                "expected_wake": {
                    "condition_id": materialized["expected_wake_condition_id"],
                    "event_kind": materialized["expected_wake_event_kind"],
                    "action": "wake_parent",
                },
                "turns": [turn],
                "events_ref": _artifact_ref(self._events_path(reentry_id)),
                "child_result_ref": None,
                "wake_evaluation": None,
                "reentry_result_ref": None,
            }
            self._save_state(state)
            return self.status(reentry_id)

    @staticmethod
    def _status_event_kind(status: str) -> str:
        return {
            "completed": "result.validated",
            "review_required": "result.review_required",
            "paused": "result.checkpointed",
            "authority_blocked": "run.authority_required",
            "failed": "result.failed",
            "interrupted": "runtime.interrupted",
        }.get(status, "result.unknown")

    @staticmethod
    def _child_runtime_lock_target(
        child_result_path: Path,
    ) -> tuple[ExternalCodexRuntime, str]:
        """Locate the canonical child lock; all authority checks repeat under it."""

        if (
            not child_result_path.is_absolute()
            or child_result_path.name != "result.json"
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result must be the canonical absolute runtime result path",
            )
        try:
            resolved_result_path = child_result_path.resolve(strict=True)
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_unavailable",
                "canonical child runtime result is unavailable",
            ) from exc
        if resolved_result_path != child_result_path or child_result_path.is_symlink():
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result path contains a symbolic or non-canonical component",
            )
        candidate = load_json(child_result_path, label="child lock target result")
        validate_json(candidate, RESULT_SCHEMA_PATH, label="child lock target result")
        session_id = str(candidate["session_id"])
        session_dir = child_result_path.parent
        if session_dir.parent.name != "sessions" or session_dir.name != _session_token(
            session_id
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result is outside the canonical session identity directory",
            )
        return ExternalCodexRuntime(session_dir.parent.parent), session_id

    @staticmethod
    def _canonical_child_runtime_receipt(
        child_result_path: Path,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Load one terminal result through its canonical durable runtime state."""

        if (
            not child_result_path.is_absolute()
            or child_result_path.name != "result.json"
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result must be the canonical absolute runtime result path",
            )
        try:
            resolved_result_path = child_result_path.resolve(strict=True)
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_unavailable",
                "canonical child runtime result is unavailable",
            ) from exc
        if resolved_result_path != child_result_path or child_result_path.is_symlink():
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result path contains a symbolic or non-canonical component",
            )
        child_result = load_json(child_result_path, label="child terminal result")
        validate_json(child_result, RESULT_SCHEMA_PATH, label="child terminal result")
        session_id = str(child_result["session_id"])
        session_dir = child_result_path.parent
        if (
            session_dir.parent.name != "sessions"
            or session_dir.name != _session_token(session_id)
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result is outside the canonical session identity directory",
            )
        state_path = session_dir / "state.json"
        if not state_path.is_file() or state_path.is_symlink():
            raise ExternalCodexRuntimeError(
                "reentry_child_state_missing",
                "canonical child runtime state receipt is unavailable",
            )
        child_state = load_json(state_path, label="child runtime state receipt")
        validate_json(child_state, STATE_SCHEMA_PATH, label="child runtime state receipt")
        result_digest = sha256_file(child_result_path)
        expected_events_path = session_dir / "events.jsonl"
        events_ref = child_result["events_ref"]
        if (
            child_state.get("schema_version") != STATE_SCHEMA_VERSION
            or child_state.get("session_id") != session_id
            or child_state.get("status") != child_result["status"]
            or child_state.get("status")
            not in {*TERMINAL_STATES, "interrupted"}
            or child_state.get("incarnation_id") != child_result["incarnation_id"]
            or child_state.get("task_id") != child_result["task_id"]
            or child_state.get("thread_id") != child_result["thread_id"]
            or child_state.get("result_path") != str(child_result_path)
            or child_state.get("result_digest") != result_digest
            or events_ref.get("artifact_ref") != str(expected_events_path)
            or child_state.get("events_digest")
            != events_ref.get("artifact_digest")
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_mismatch",
                "child durable state does not bind the supplied terminal result",
            )
        verified_events_path = _verified_artifact_ref_path(
            events_ref, label="canonical child event stream"
        )
        if verified_events_path != expected_events_path:
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_mismatch",
                "child event receipt is outside its canonical session directory",
            )
        event_count = sum(
            1
            for _line_number, _line in _iter_jsonl_bytes(
                verified_events_path,
                failure_code="reentry_child_receipt_mismatch",
                label="canonical child event stream",
            )
        )
        if event_count != int(child_state["last_event_sequence"]) + 1:
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_mismatch",
                "child event receipt differs from the durable terminal sequence",
            )
        return child_result, child_state, _artifact_ref(child_result_path)

    @staticmethod
    def _verify_child_wake_event(
        result: Mapping[str, Any], binding: AgentIncarnationBinding
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if result["events_ref"] not in result["evidence_refs"]:
            raise ExternalCodexRuntimeError(
                "reentry_child_event_unbound",
                "child result does not bind its event stream as terminal evidence",
            )
        event_kind = ExternalCodexParentReentry._status_event_kind(str(result["status"]))
        condition = next(
            (
                item
                for item in binding.wake_policy.conditions
                if item.event_kind == event_kind
            ),
            None,
        )
        expected = {
            "event_kind": event_kind,
            "condition_id": condition.condition_id if condition is not None else None,
            "action": (
                condition.action
                if condition is not None
                else binding.wake_policy.default_action
            ),
            "wake_parent": condition is not None and condition.action == "wake_parent",
            "reason": (
                condition.description
                if condition is not None
                else "No exact wake condition matched; runtime applied the configured default."
            ),
        }
        if result["wake_evaluation"] != expected:
            raise ExternalCodexRuntimeError(
                "reentry_child_wake_mismatch",
                "child result wake evaluation differs from the immutable binding",
            )
        events_path = _verified_artifact_ref_path(
            result["events_ref"], label="child event stream"
        )
        matches: list[dict[str, Any]] = []
        for line_number, line in _iter_jsonl_bytes(
            events_path,
            failure_code="reentry_child_event_invalid",
            label="child event stream",
        ):
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExternalCodexRuntimeError(
                    "reentry_child_event_invalid",
                    f"child event line {line_number} is invalid",
                ) from exc
            if not isinstance(event, dict):
                raise ExternalCodexRuntimeError(
                    "reentry_child_event_invalid",
                    f"child event line {line_number} is not an object",
                )
            if (
                event.get("event_type") == "external_agent.wake_evaluated"
                and event.get("payload") == expected
            ):
                matches.append(event)
        if len(matches) != 1:
            raise ExternalCodexRuntimeError(
                "reentry_child_event_missing",
                "child stream does not contain one exact wake evaluation event",
            )
        return expected, matches[0]

    @staticmethod
    def _distilled_child_return(
        result: Mapping[str, Any],
        child_result_ref: Mapping[str, Any],
        event: Mapping[str, Any],
    ) -> dict[str, Any]:
        report_summary: str | None = None
        report_findings: list[Any] = []
        report_ref = result.get("report_ref")
        if isinstance(report_ref, dict):
            report = _load_verified_json_ref(report_ref, label="child model report")
            summary = report.get("summary")
            findings = report.get("findings")
            if isinstance(summary, str):
                report_summary = summary
            if isinstance(findings, list):
                report_findings = findings
        return {
            "child_result_ref": dict(child_result_ref),
            "child_status": result["status"],
            "child_task_id": result["task_id"],
            "child_incarnation_id": result["incarnation_id"],
            "child_thread_id": result["thread_id"],
            "wake_evaluation": result["wake_evaluation"],
            "observed_event_digest": canonical_digest(event),
            "report_ref": report_ref,
            "report_summary": report_summary,
            "report_findings": report_findings,
            "changed_paths": result["changed_paths"],
            "usage": result["usage"],
            "usage_observation": result["usage_observation"],
        }

    @staticmethod
    def _reentry_prompt(
        obligation: Mapping[str, Any],
        state: Mapping[str, Any],
        distilled: Mapping[str, Any],
    ) -> str:
        payload = {
            "reentry_id": obligation["reentry_id"],
            "continuation_id": state["continuation_id"],
            "deferred_parent_decisions": obligation["deferred_parent_decisions"],
            "distilled_child_return": distilled,
        }
        return (
            "Событийный runtime разбудил тот же parent Sol thread после завершения "
            "child inference. Не используй инструменты и не считывай дополнительные "
            "файлы: оцени только digest-bound distilled return. Пользователь остаётся "
            "единственным human authority. Для run.authority_required верни "
            "decision=authority_review_required и next_action=request_human_authority. "
            "Скопируй все identity и digest поля дословно; не заявляй acceptance или "
            "внешний эффект.\n\n"
            + "<parent_payload>\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n</parent_payload>"
        )

    @staticmethod
    def _validate_reentry_output(
        output: Mapping[str, Any],
        state: Mapping[str, Any],
        distilled: Mapping[str, Any],
    ) -> None:
        child_ref = distilled["child_result_ref"]
        if (
            output["reentry_id"] != state["reentry_id"]
            or output["continuation_id"] != state["continuation_id"]
            or output["child_task_id"] != state["child_task_id"]
            or output["child_result_digest"] != child_ref["artifact_digest"]
            or output["observed_event_digest"] != distilled["observed_event_digest"]
            or output["decision"] != "authority_review_required"
            or output["next_action"] != "request_human_authority"
            or not str(output["summary"]).strip()
        ):
            raise ExternalCodexRuntimeError(
                "reentry_parent_result_mismatch",
                "parent re-entry output differs from the admitted child event",
            )

    def reenter_parent(
        self, reentry_id: str, child_result_path: str | Path
    ) -> dict[str, Any]:
        with self._lock(reentry_id):
            state = self._load_state(reentry_id)
            if state["status"] != "waiting":
                raise ExternalCodexRuntimeError(
                    "reentry_state_not_waiting",
                    f"parent re-entry is not waiting: {state['status']}",
                )
            obligation = _load_verified_json_ref(
                state["obligation_ref"],
                label="materialized parent obligation",
                schema_path=PARENT_OBLIGATION_SCHEMA_PATH,
            )
            task, binding, realization = self._validate_obligation(obligation)
            child_path = Path(child_result_path)
            child_runtime, child_session_id = self._child_runtime_lock_target(
                child_path
            )
            with child_runtime._lock(child_session_id):
                child_result, _child_state, child_ref = (
                    self._canonical_child_runtime_receipt(child_path)
                )
                if (
                    child_result["task_id"] != state["child_task_id"]
                    or child_result["incarnation_id"] != state["child_incarnation_id"]
                    or child_result["task_id"] != task["task_id"]
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_child_identity_mismatch",
                        "child terminal result belongs to another task or incarnation",
                    )
                wake, observed_event = self._verify_child_wake_event(
                    child_result, binding
                )
                self._append_event(
                    reentry_id,
                    event_type="external_parent.child_event_admitted",
                    payload={
                        "child_result_digest": child_ref["artifact_digest"],
                        "child_result_ref": child_ref,
                        "observed_event_digest": canonical_digest(observed_event),
                        "wake_evaluation": wake,
                    },
                    significance=("parent_wake" if wake["wake_parent"] else "filtered"),
                )
            state["child_result_ref"] = child_ref
            state["wake_evaluation"] = wake
            expected = state["expected_wake"]
            exact_expected_wake = (
                wake["condition_id"] == expected["condition_id"]
                and wake["event_kind"] == expected["event_kind"]
                and wake["action"] == expected["action"]
                and wake["wake_parent"] is True
            )
            if not exact_expected_wake:
                state["status"] = "filtered"
                self._append_event(
                    reentry_id,
                    event_type="external_parent.wake_filtered",
                    payload={"wake_evaluation": wake},
                    significance="terminal",
                )
                self._save_state(state)
                return self.status(reentry_id)

            distilled = self._distilled_child_return(
                child_result, child_ref, observed_event
            )
            distilled_path = self._reentry_dir(reentry_id) / "distilled-child-return.json"
            _atomic_write_json(distilled_path, distilled, mode=0o400)
            state["status"] = "reentering"
            self._append_event(
                reentry_id,
                event_type="external_parent.reentry_started",
                payload={
                    "parent_thread_id": state["parent_thread_id"],
                    "distilled_return_ref": _artifact_ref(distilled_path),
                },
                significance="reentry",
            )
            self._save_state(state)
            try:
                turn, output = self._run_parent_turn(
                    obligation,
                    realization,
                    kind="reentry",
                    prompt=self._reentry_prompt(obligation, state, distilled),
                    thread_id=str(state["parent_thread_id"]),
                )
                self._validate_reentry_output(output, state, distilled)
            except Exception as exc:
                state["status"] = "failed"
                self._append_event(
                    reentry_id,
                    event_type="external_parent.reentry_failed",
                    payload={"failure_type": type(exc).__name__},
                    significance="terminal",
                )
                self._save_state(state)
                raise
            state["turns"] = [*state["turns"], turn]
            state["reentry_result_ref"] = turn["output_ref"]
            state["status"] = "reentered"
            self._append_event(
                reentry_id,
                event_type="external_parent.reentry_completed",
                payload={
                    "parent_thread_id": turn["thread_id"],
                    "result_digest": turn["output_ref"]["artifact_digest"],
                    "next_action": output["next_action"],
                    "turn": turn,
                    "reentry_result_ref": turn["output_ref"],
                },
                significance="authority",
            )
            self._save_state(state)
            return self.status(reentry_id)

    def status(self, reentry_id: str) -> dict[str, Any]:
        state = self._load_state(reentry_id)
        return {
            "state": state,
            "state_ref": _artifact_ref(self._state_path(reentry_id)),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=(
            "preflight",
            "start",
            "run-to-terminal",
            "status",
            "events",
            "result",
            "resume",
            "interrupt",
            "export-a2a-result",
            "yield-parent",
            "reenter-parent",
            "reentry-status",
        ),
    )
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--profile", default=str(PROFILE_PATH))
    parser.add_argument("--launch")
    parser.add_argument("--owner-execution-request")
    parser.add_argument("--session-id")
    parser.add_argument("--after-sequence", type=int, default=-1)
    parser.add_argument("--resume-request")
    parser.add_argument("--reviewer-session-id")
    parser.add_argument("--reviewer-state-root")
    parser.add_argument("--summon-request")
    parser.add_argument("--output")
    parser.add_argument("--obligation")
    parser.add_argument("--reentry-id")
    parser.add_argument("--child-result")
    return parser


def _require(value: str | None, flag: str) -> str:
    if not value:
        raise ExternalCodexRuntimeError(
            "missing_argument", f"{flag} is required for this operation"
        )
    return value


def _write_response(*, ok: bool, result: Any = None, error: ExternalCodexRuntimeError | None = None) -> None:
    payload: dict[str, Any] = {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "ok": ok,
    }
    if ok:
        payload["result"] = result
    else:
        assert error is not None
        payload["error_code"] = error.code
        payload["message"] = str(error)
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: Any
        if args.operation in {"yield-parent", "reenter-parent", "reentry-status"}:
            reentry = ExternalCodexParentReentry(
                args.state_root, profile_path=args.profile
            )
            if args.operation == "yield-parent":
                result = reentry.yield_parent(
                    _require(args.obligation, "--obligation")
                )
            elif args.operation == "reenter-parent":
                result = reentry.reenter_parent(
                    _require(args.reentry_id, "--reentry-id"),
                    _require(args.child_result, "--child-result"),
                )
            else:
                result = reentry.status(
                    _require(args.reentry_id, "--reentry-id")
                )
        else:
            runtime = ExternalCodexRuntime(args.state_root, profile_path=args.profile)
            if args.operation == "preflight":
                result = runtime.preflight(
                    _require(args.launch, "--launch"),
                    owner_request_path=args.owner_execution_request,
                )
            elif args.operation == "start":
                result = runtime.start(
                    _require(args.launch, "--launch"),
                    owner_request_path=args.owner_execution_request,
                )
            elif args.operation == "run-to-terminal":
                result = runtime.run_to_terminal(
                    _require(args.launch, "--launch"),
                    owner_request_path=args.owner_execution_request,
                )
            elif args.operation == "status":
                result = runtime.status(_require(args.session_id, "--session-id"))
            elif args.operation == "events":
                result = runtime.events(
                    _require(args.session_id, "--session-id"),
                    after_sequence=args.after_sequence,
                )
            elif args.operation == "result":
                result = runtime.result(_require(args.session_id, "--session-id"))
            elif args.operation == "resume":
                result = runtime.resume(
                    _require(args.session_id, "--session-id"),
                    _require(args.resume_request, "--resume-request"),
                )
            elif args.operation == "interrupt":
                result = runtime.interrupt(_require(args.session_id, "--session-id"))
            else:
                result = runtime.export_a2a_result(
                    _require(args.session_id, "--session-id"),
                    reviewer_session_id=_require(
                        args.reviewer_session_id, "--reviewer-session-id"
                    ),
                    reviewer_state_root=args.reviewer_state_root,
                    summon_request_path=_require(args.summon_request, "--summon-request"),
                    output_path=_require(args.output, "--output"),
                )
        _write_response(ok=True, result=result)
        return 0
    except ExternalCodexRuntimeError as exc:
        _write_response(ok=False, error=exc)
        return 2
    except Exception as exc:  # pragma: no cover - last-resort fail-closed envelope
        error = ExternalCodexRuntimeError(
            "unexpected_runtime_error", f"unexpected {type(exc).__name__}"
        )
        _write_response(ok=False, error=error)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
