#!/usr/bin/env python3
"""Run an isolated SEP-2663 lifecycle proof and one read-only owner pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TASKS_EXTENSION_ID = "io.modelcontextprotocol/tasks"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _wire_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_root(path: Path) -> Path:
    result = path.expanduser().absolute()
    for component in (*reversed(result.parents), result):
        if component.exists() and component.is_symlink():
            raise SystemExit("tasks pilot state root cannot traverse a symlink")
    result.mkdir(parents=True, exist_ok=True, mode=0o700)
    if result.is_symlink() or not result.is_dir():
        raise SystemExit("tasks pilot state root must be a non-symlink directory")
    os.chmod(result, 0o700)
    return result


def _write_private(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


class _PayloadResolver:
    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}
        self.errors: dict[str, dict[str, Any]] = {}
        self.inputs: dict[str, dict[str, Any]] = {}

    def resolve_result(self, record: Any) -> dict[str, Any]:
        return self.results[record.result_ref]

    def resolve_error(self, record: Any) -> dict[str, Any]:
        return self.errors[record.error_ref]

    def resolve_input_request(self, record: Any, request: Any) -> dict[str, Any]:
        del record
        return self.inputs[request.prompt_ref]


def _context(
    request_context_type: Any,
    method: str,
    name: str,
    *,
    principal: str = "tasks-pilot-principal",
    declares_tasks: bool = True,
) -> Any:
    capabilities = (
        {"extensions": {TASKS_EXTENSION_ID: {}}} if declares_tasks else {}
    )
    return request_context_type(
        principal_id=principal,
        organ_id="abyss-stack",
        contour_id="read",
        protocol_version="2026-07-28",
        client_capabilities=capabilities,
        transport="streamable_http",
        headers={"Mcp-Method": method, "Mcp-Name": name},
    )


def _record_case(cases: list[dict[str, Any]], name: str, check: bool, **facts: Any) -> None:
    cases.append({"case": name, "passed": bool(check), "facts": facts})
    if not check:
        raise RuntimeError(f"tasks pilot case failed: {name}")


def _run(args: argparse.Namespace) -> dict[str, Any]:
    sdk_root = Path(args.aoa_sdk_root).expanduser().resolve(strict=True)
    sys.path.insert(0, str(sdk_root / "src"))
    from aoa_sdk.contracts.tasks import TaskInputRequest
    from aoa_sdk.organs import (
        FileTaskStore,
        MCPTaskRequestContext,
        MCPTasksAdapter,
        MCPTasksAdapterError,
        TaskStoreLimits,
    )
    from aoa_sdk.organs.registry import sha256_digest

    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%S.%fZ")
    state_root = _safe_root(Path(args.state_root))
    run_root = state_root / "runs" / run_id
    run_root.mkdir(parents=True, mode=0o700)
    os.chmod(run_root, 0o700)
    private_root = run_root / "private"
    private_root.mkdir(mode=0o700)
    cases: list[dict[str, Any]] = []
    claims: list[str] = []

    base = started_at
    payloads = _PayloadResolver()
    store = FileTaskStore(private_root / "synthetic-tasks")
    cancelled_owner_runs: list[str] = []
    adapter = MCPTasksAdapter(
        store,
        payloads,
        enabled=True,
        cancel_sink=lambda record: cancelled_owner_runs.append(record.owner_run_ref),
        maximum_input_response_bytes=512,
    )

    sync_fallback = adapter.create_task_result(
        _context(
            MCPTaskRequestContext,
            "tools/call",
            "quick_read",
            declares_tasks=False,
        ),
        tool_name="quick_read",
        arguments={"scope": "bounded"},
        owner_run_ref="owner://abyss-stack/run/quick-read",
        idempotency_key="quick-read",
        ttl_seconds=60,
        poll_interval_ms=100,
        now=base,
    )
    _record_case(
        cases,
        "short_sync_fallback",
        sync_fallback is None,
        result_type="complete",
        task_created=False,
    )

    created = adapter.create_task_result(
        _context(MCPTaskRequestContext, "tools/call", "slow_read"),
        tool_name="slow_read",
        arguments={"scope": "synthetic"},
        owner_run_ref="owner://abyss-stack/run/slow-read",
        idempotency_key="slow-read",
        ttl_seconds=600,
        poll_interval_ms=100,
        now=base,
    )
    assert created is not None
    task_id = created["taskId"]
    working = adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", task_id),
        task_id=task_id,
        now=base + timedelta(milliseconds=200),
    )
    owner_result = {
        "content": [{"type": "text", "text": "synthetic long read complete"}],
        "isError": False,
    }
    result_ref = "owner://abyss-stack/result/slow-read"
    payloads.results[result_ref] = owner_result
    current = store.get(
        task_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        now=base + timedelta(milliseconds=250),
    )
    store.complete(
        task_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        expected_revision=current.revision,
        result_ref=result_ref,
        result_digest=sha256_digest(owner_result),
        evidence_refs=("owner://abyss-stack/evidence/slow-read",),
        now=base + timedelta(milliseconds=300),
    )
    completed = adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", task_id),
        task_id=task_id,
        now=base + timedelta(milliseconds=400),
    )
    _record_case(
        cases,
        "long_task_poll_complete",
        working["status"] == "working"
        and completed["status"] == "completed"
        and completed["result"] == owner_result,
        create_result_type=created["resultType"],
        terminal_status=completed["status"],
        task_id_digest=_digest(task_id),
    )

    failed_created = adapter.create_task_result(
        _context(MCPTaskRequestContext, "tools/call", "protocol_failure"),
        tool_name="protocol_failure",
        arguments={},
        owner_run_ref="owner://abyss-stack/run/protocol-failure",
        idempotency_key="protocol-failure",
        ttl_seconds=600,
        poll_interval_ms=100,
        now=base + timedelta(seconds=1),
    )
    assert failed_created is not None
    failed_id = failed_created["taskId"]
    owner_error = {"code": -32603, "message": "Synthetic owner worker failed"}
    error_ref = "owner://abyss-stack/error/protocol-failure"
    payloads.errors[error_ref] = owner_error
    store.fail(
        failed_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        expected_revision=1,
        error_ref=error_ref,
        error_digest=sha256_digest(owner_error),
        now=base + timedelta(seconds=1, milliseconds=100),
    )
    failed = adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", failed_id),
        task_id=failed_id,
        now=base + timedelta(seconds=1, milliseconds=200),
    )
    _record_case(
        cases,
        "jsonrpc_failure_inlined",
        failed["status"] == "failed" and failed["error"] == owner_error,
        terminal_status=failed["status"],
        error_code=failed["error"]["code"],
    )

    input_created = adapter.create_task_result(
        _context(MCPTaskRequestContext, "tools/call", "interactive_read"),
        tool_name="interactive_read",
        arguments={},
        owner_run_ref="owner://abyss-stack/run/interactive-read",
        idempotency_key="interactive-read",
        ttl_seconds=600,
        poll_interval_ms=100,
        now=base + timedelta(seconds=2),
    )
    assert input_created is not None
    input_id = input_created["taskId"]
    for offset, key in enumerate(("scope", "detail"), start=1):
        ref = f"owner://abyss-stack/task-input/{key}"
        payloads.inputs[ref] = {
            "method": "elicitation/create",
            "params": {
                "mode": "form",
                "message": f"Provide {key}",
                "requestedSchema": {"type": "object"},
            },
        }
        record = store.get(
            input_id,
            principal_id="tasks-pilot-principal",
            organ_id="abyss-stack",
            contour_id="read",
            now=base + timedelta(seconds=2, milliseconds=offset * 10),
        )
        store.require_input(
            input_id,
            principal_id="tasks-pilot-principal",
            organ_id="abyss-stack",
            contour_id="read",
            expected_revision=record.revision,
            request=TaskInputRequest(
                request_key=key,
                prompt_ref=ref,
                input_schema_ref=f"owner://abyss-stack/schema/{key}",
                input_schema_digest=_digest({"type": "object", "key": key}),
                requested_at=base + timedelta(seconds=2, milliseconds=offset * 10),
                expires_at=base + timedelta(seconds=60),
            ),
            now=base + timedelta(seconds=2, milliseconds=offset * 10),
        )
    input_required = adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", input_id),
        task_id=input_id,
        now=base + timedelta(seconds=2, milliseconds=100),
    )
    adapter.update_task(
        _context(MCPTaskRequestContext, "tasks/update", input_id),
        task_id=input_id,
        input_responses={"scope": {"action": "accept", "content": {"value": "runtime"}}},
        now=base + timedelta(seconds=2, milliseconds=200),
    )
    partial = adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", input_id),
        task_id=input_id,
        now=base + timedelta(seconds=2, milliseconds=300),
    )
    duplicate_ack = adapter.update_task(
        _context(MCPTaskRequestContext, "tasks/update", input_id),
        task_id=input_id,
        input_responses={"scope": {"action": "accept", "content": {"value": "runtime"}}},
        now=base + timedelta(seconds=2, milliseconds=350),
    )
    adapter.update_task(
        _context(MCPTaskRequestContext, "tasks/update", input_id),
        task_id=input_id,
        input_responses={"detail": {"action": "accept", "content": {"value": "bounded"}}},
        now=base + timedelta(seconds=2, milliseconds=400),
    )
    resumed = adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", input_id),
        task_id=input_id,
        now=base + timedelta(seconds=2, milliseconds=500),
    )
    _record_case(
        cases,
        "input_required_partial_duplicate_resume",
        set(input_required["inputRequests"]) == {"scope", "detail"}
        and set(partial["inputRequests"]) == {"detail"}
        and duplicate_ack == {"resultType": "complete"}
        and resumed["status"] == "working",
        initial_inputs=2,
        remaining_after_partial=1,
        duplicate_ack=True,
    )

    cancel_created = adapter.create_task_result(
        _context(MCPTaskRequestContext, "tools/call", "cancellable_read"),
        tool_name="cancellable_read",
        arguments={},
        owner_run_ref="owner://abyss-stack/run/cancellable-read",
        idempotency_key="cancellable-read",
        ttl_seconds=600,
        poll_interval_ms=100,
        now=base + timedelta(seconds=3),
    )
    assert cancel_created is not None
    cancel_id = cancel_created["taskId"]
    cancel_ack = adapter.cancel_task(
        _context(MCPTaskRequestContext, "tasks/cancel", cancel_id),
        task_id=cancel_id,
        now=base + timedelta(seconds=3, milliseconds=100),
    )
    cancel_record = store.get(
        cancel_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        now=base + timedelta(seconds=3, milliseconds=150),
    )
    store.acknowledge_cancel(
        cancel_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        expected_revision=cancel_record.revision,
        accepted=True,
        now=base + timedelta(seconds=3, milliseconds=200),
    )
    cancelled = adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", cancel_id),
        task_id=cancel_id,
        now=base + timedelta(seconds=3, milliseconds=300),
    )
    _record_case(
        cases,
        "cooperative_cancellation",
        cancel_ack == {"resultType": "complete"}
        and cancelled["status"] == "cancelled"
        and cancelled_owner_runs == ["owner://abyss-stack/run/cancellable-read"],
        cancellation_intent_persisted=True,
        owner_acknowledged=True,
    )

    race_created = adapter.create_task_result(
        _context(MCPTaskRequestContext, "tools/call", "race_read"),
        tool_name="race_read",
        arguments={},
        owner_run_ref="owner://abyss-stack/run/race-read",
        idempotency_key="race-read",
        ttl_seconds=600,
        poll_interval_ms=100,
        now=base + timedelta(seconds=4),
    )
    assert race_created is not None
    race_id = race_created["taskId"]
    race_result = {"content": [{"type": "text", "text": "won by completion"}]}
    race_ref = "owner://abyss-stack/result/race-read"
    payloads.results[race_ref] = race_result
    store.complete(
        race_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        expected_revision=1,
        result_ref=race_ref,
        result_digest=sha256_digest(race_result),
        now=base + timedelta(seconds=4, milliseconds=100),
    )
    sink_count = len(cancelled_owner_runs)
    race_ack = adapter.cancel_task(
        _context(MCPTaskRequestContext, "tasks/cancel", race_id),
        task_id=race_id,
        now=base + timedelta(seconds=4, milliseconds=200),
    )
    _record_case(
        cases,
        "cancellation_completion_race",
        race_ack == {"resultType": "complete"}
        and len(cancelled_owner_runs) == sink_count,
        terminal_cancel_idempotent=True,
        cancellation_sink_called=False,
    )

    restart_created = adapter.create_task_result(
        _context(MCPTaskRequestContext, "tools/call", "restart_read"),
        tool_name="restart_read",
        arguments={},
        owner_run_ref="owner://abyss-stack/run/restart-read",
        idempotency_key="restart-read",
        ttl_seconds=600,
        poll_interval_ms=100,
        now=base + timedelta(seconds=5),
    )
    assert restart_created is not None
    restart_id = restart_created["taskId"]
    restarted_store = FileTaskStore(private_root / "synthetic-tasks")
    restarted_adapter = MCPTasksAdapter(
        restarted_store,
        payloads,
        enabled=True,
    )
    resumed_after_restart = restarted_adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", restart_id),
        task_id=restart_id,
        now=base + timedelta(seconds=5, milliseconds=200),
    )
    _record_case(
        cases,
        "worker_and_client_restart_resume",
        resumed_after_restart["status"] == "working",
        durable_handle_reopened=True,
        owner_run_ref_retained=True,
    )

    expiry_store = FileTaskStore(private_root / "expiry-tasks")
    expiry_adapter = MCPTasksAdapter(expiry_store, payloads, enabled=True)
    expired_created = expiry_adapter.create_task_result(
        _context(MCPTaskRequestContext, "tools/call", "expiring_read"),
        tool_name="expiring_read",
        arguments={},
        owner_run_ref="owner://abyss-stack/run/expiring-read",
        idempotency_key="expiring-read",
        ttl_seconds=1,
        poll_interval_ms=100,
        now=base + timedelta(seconds=6),
    )
    assert expired_created is not None
    expired_id = expired_created["taskId"]
    expiry_store.expire(
        expired_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        expected_revision=1,
        now=base + timedelta(seconds=8),
    )
    expired = expiry_adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", expired_id),
        task_id=expired_id,
        now=base + timedelta(seconds=8, milliseconds=100),
    )
    removed = expiry_store.cleanup_expired(now=base + timedelta(seconds=9))
    _record_case(
        cases,
        "ttl_expiry_and_cleanup",
        expired["status"] == "failed" and removed == 1,
        wire_status=expired["status"],
        removed_records=removed,
    )

    denied = False
    try:
        adapter.get_task(
            _context(
                MCPTaskRequestContext,
                "tasks/get",
                restart_id,
                principal="different-principal",
            ),
            task_id=restart_id,
            now=base + timedelta(seconds=9),
        )
    except MCPTasksAdapterError as exc:
        denied = exc.code == -32602 and exc.message == "Unknown task"
    unknown = False
    try:
        adapter.get_task(
            _context(MCPTaskRequestContext, "tasks/get", "unknown-task"),
            task_id="unknown-task",
            now=base + timedelta(seconds=9),
        )
    except MCPTasksAdapterError as exc:
        unknown = exc.code == -32602 and exc.message == "Unknown task"
    _record_case(
        cases,
        "wrong_principal_and_unknown_are_indistinguishable",
        denied and unknown,
        error_code=-32602,
        disclosure="collapsed",
    )

    limit_store = FileTaskStore(
        private_root / "limit-tasks",
        limits=TaskStoreLimits(
            maximum_active_tasks=1,
            maximum_active_tasks_per_principal=1,
            maximum_arguments_bytes=64,
            maximum_record_bytes=256 * 1024,
            maximum_inputs=1,
            maximum_ttl_seconds=60,
        ),
    )
    limit_adapter = MCPTasksAdapter(
        limit_store,
        payloads,
        enabled=True,
        maximum_input_response_bytes=64,
    )
    limited_created = limit_adapter.create_task_result(
        _context(MCPTaskRequestContext, "tools/call", "limited_read"),
        tool_name="limited_read",
        arguments={},
        owner_run_ref="owner://abyss-stack/run/limited-read",
        idempotency_key="limited-read-one",
        ttl_seconds=60,
        poll_interval_ms=500,
        now=base + timedelta(seconds=10),
    )
    assert limited_created is not None
    limited_task_id = limited_created["taskId"]
    limited_record = limit_store.get(
        limited_task_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        now=base + timedelta(seconds=10, milliseconds=50),
    )
    rate_blocked = False
    limit_adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", limited_record.task_id),
        task_id=limited_record.task_id,
        now=base + timedelta(seconds=10, milliseconds=100),
    )
    try:
        limit_adapter.get_task(
            _context(MCPTaskRequestContext, "tasks/get", limited_record.task_id),
            task_id=limited_record.task_id,
            now=base + timedelta(seconds=10, milliseconds=200),
        )
    except MCPTasksAdapterError as exc:
        rate_blocked = exc.code == -32029 and exc.http_status == 429
    limit_input_ref = "owner://abyss-stack/task-input/limited"
    payloads.inputs[limit_input_ref] = {
        "method": "elicitation/create",
        "params": {"mode": "form", "message": "bounded", "requestedSchema": {}},
    }
    limit_store.require_input(
        limited_record.task_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        expected_revision=limited_record.revision,
        request=TaskInputRequest(
            request_key="limited-input",
            prompt_ref=limit_input_ref,
            input_schema_ref="owner://abyss-stack/schema/limited-input",
            input_schema_digest=_digest({"type": "object", "limited": True}),
            requested_at=base + timedelta(seconds=10, milliseconds=300),
            expires_at=base + timedelta(seconds=30),
        ),
        now=base + timedelta(seconds=10, milliseconds=300),
    )
    payload_blocked = False
    try:
        limit_adapter.update_task(
            _context(MCPTaskRequestContext, "tasks/update", limited_record.task_id),
            task_id=limited_record.task_id,
            input_responses={"limited-input": {"content": "x" * 128}},
            now=base + timedelta(seconds=10, milliseconds=400),
        )
    except MCPTasksAdapterError as exc:
        payload_blocked = exc.code == -32602
    quota_blocked = False
    try:
        limit_adapter.create_task_result(
            _context(MCPTaskRequestContext, "tools/call", "limited_read"),
            tool_name="limited_read",
            arguments={"second": True},
            owner_run_ref="owner://abyss-stack/run/limited-read-two",
            idempotency_key="limited-read-two",
            ttl_seconds=60,
            poll_interval_ms=500,
            now=base + timedelta(seconds=10, milliseconds=1),
        )
    except MCPTasksAdapterError as exc:
        quota_blocked = exc.code == -32602
    _record_case(
        cases,
        "quota_rate_and_payload_policy",
        quota_blocked and rate_blocked and payload_blocked,
        active_task_quota=1,
        poll_rate_limited=True,
        maximum_input_response_bytes=64,
        oversized_input_rejected=True,
    )

    owner_started = datetime.now(timezone.utc)
    owner_store = FileTaskStore(private_root / "owner-pilot-tasks")
    owner_payloads = _PayloadResolver()
    owner_adapter = MCPTasksAdapter(owner_store, owner_payloads, enabled=True)
    owner_created = owner_adapter.create_task_result(
        _context(MCPTaskRequestContext, "tools/call", "bounded_diagnostic_snapshot"),
        tool_name="bounded_diagnostic_snapshot",
        arguments={"truth_goal": "deployed"},
        owner_run_ref=f"owner://abyss-stack/diagnostic/tasks-pilot/{run_id}",
        idempotency_key=f"diagnostic-{run_id.lower()}",
        ttl_seconds=900,
        poll_interval_ms=250,
        now=owner_started,
    )
    assert owner_created is not None
    owner_task_id = owner_created["taskId"]
    owner_working = owner_adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", owner_task_id),
        task_id=owner_task_id,
        now=owner_started + timedelta(milliseconds=300),
    )
    diagnostic_path = private_root / "owner-diagnostic-session.json"
    stack_source = Path(args.stack_source).expanduser().resolve(strict=True)
    command = (
        sys.executable,
        str(
            stack_source
            / "mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py"
        ),
        "--truth-goal",
        "deployed",
        "--write",
        str(diagnostic_path),
    )
    owner_command_started = time.monotonic()
    completed_process = subprocess.run(
        command,
        cwd=stack_source,
        env={**os.environ, "AOA_STACK_ROOT": args.deployed_stack_root},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    owner_duration_ms = int((time.monotonic() - owner_command_started) * 1000)
    _write_private(
        private_root / "owner-command.json",
        {
            "argv": [
                "python",
                "mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py",
                "--truth-goal",
                "deployed",
                "--write",
                "<private-owner-diagnostic-session>",
            ],
            "returncode": completed_process.returncode,
            "stdout": completed_process.stdout,
            "stderr": completed_process.stderr,
            "duration_ms": owner_duration_ms,
        },
    )
    if not diagnostic_path.is_file() or diagnostic_path.is_symlink():
        raise RuntimeError("read-only owner diagnostic did not produce its result")
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    owner_result = {
        "content": [
            {
                "type": "text",
                "text": "Bounded abyss-stack diagnostic snapshot completed.",
            }
        ],
        "structuredContent": {"diagnosticSession": diagnostic},
        "isError": completed_process.returncode != 0,
    }
    owner_result_ref = f"owner://abyss-stack/diagnostic-result/{run_id}"
    owner_payloads.results[owner_result_ref] = owner_result
    owner_current = owner_store.get(
        owner_task_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        now=datetime.now(timezone.utc),
    )
    owner_store.complete(
        owner_task_id,
        principal_id="tasks-pilot-principal",
        organ_id="abyss-stack",
        contour_id="read",
        expected_revision=owner_current.revision,
        result_ref=owner_result_ref,
        result_digest=sha256_digest(owner_result),
        evidence_refs=(
            f"owner://abyss-stack/diagnostic-evidence/{_digest(diagnostic)[7:]}",
        ),
        now=datetime.now(timezone.utc),
    )
    # Re-open both store and adapter to model a disconnected client and a
    # restarted adapter process.  Owner work is not executed again.
    owner_resumed_adapter = MCPTasksAdapter(
        FileTaskStore(private_root / "owner-pilot-tasks"),
        owner_payloads,
        enabled=True,
    )
    owner_terminal = owner_resumed_adapter.get_task(
        _context(MCPTaskRequestContext, "tasks/get", owner_task_id),
        task_id=owner_task_id,
        now=datetime.now(timezone.utc),
    )
    _record_case(
        cases,
        "useful_read_only_owner_diagnostic",
        owner_working["status"] == "working"
        and owner_terminal["status"] == "completed"
        and owner_terminal["result"]["structuredContent"]["diagnosticSession"]
        == diagnostic,
        owner="abyss-stack",
        authority="diagnostic_session_v1",
        command_returncode=completed_process.returncode,
        owner_duration_ms=owner_duration_ms,
        task_resumed_after_adapter_restart=True,
        owner_rerun_count=0,
        diagnostic_digest=_digest(diagnostic),
    )
    claims.extend(
        (
            "The adapter preserved one read-only abyss-stack diagnostic result across adapter restart without rerunning owner work.",
            "The task terminal state reflects owner-issued bytes; it does not imply repair, admission, proof, acceptance, or effect authority.",
            "Codex was not the Tasks consumer in this pilot; current Codex remains ineligible until it advertises the extension on the real request wire.",
            "Notifications were not tested because current subscriptions/listen support cannot yet carry the extension filter end to end.",
        )
    )

    finished_at = datetime.now(timezone.utc)
    public = {
        "schema_version": "abyss_mcp_tasks_pilot_v1",
        "run_id": run_id,
        "started_at": _wire_time(started_at),
        "finished_at": _wire_time(finished_at),
        "protocol_version": "2026-07-28",
        "extension_id": TASKS_EXTENSION_ID,
        "adapter_feature_gate_enabled": True,
        "production_enabled": False,
        "client_kind": "abyss-synthetic-capable-client",
        "codex_consumer_used": False,
        "all_cases_passed": all(item["passed"] for item in cases),
        "case_count": len(cases),
        "cases": cases,
        "notifications": {
            "tested": False,
            "reason": "subscriptions_listen_extension_filter_not_proven",
        },
        "owner_pilot": {
            "owner": "abyss-stack",
            "operation": "bounded_diagnostic_snapshot",
            "effect_class": "observe",
            "diagnostic_digest": _digest(diagnostic),
            "command_returncode": completed_process.returncode,
            "duration_ms": owner_duration_ms,
            "resumed_after_adapter_restart": True,
            "owner_rerun_count": 0,
        },
        "claim_limits": claims,
    }
    _write_private(run_root / "public-safe.json", public)
    private_summary = {
        **public,
        "private": {
            "run_root": str(run_root),
            "owner_task_id_digest": _digest(owner_task_id),
            "owner_result_file_digest": "sha256:"
            + hashlib.sha256(diagnostic_path.read_bytes()).hexdigest(),
            "sdk_source_revision": subprocess.run(
                ("git", "rev-parse", "HEAD"),
                cwd=sdk_root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
            "stack_source_revision": subprocess.run(
                ("git", "rev-parse", "HEAD"),
                cwd=stack_source,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
        },
    }
    _write_private(run_root / "private-summary.json", private_summary)
    return {
        "run_root": str(run_root),
        "public_safe": str(run_root / "public-safe.json"),
        "all_cases_passed": public["all_cases_passed"],
        "case_count": len(cases),
        "owner_pilot_status": owner_terminal["status"],
        "owner_diagnostic_digest": _digest(diagnostic),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aoa-sdk-root", required=True)
    parser.add_argument("--stack-source", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument(
        "--deployed-stack-root",
        default="/srv/AbyssOS/abyss-stack",
    )
    args = parser.parse_args()
    result = _run(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["all_cases_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
