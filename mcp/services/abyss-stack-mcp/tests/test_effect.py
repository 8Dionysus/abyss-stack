from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import abyss_stack_mcp.effect_server as effect_server_module

from abyss_stack_mcp.effect import (
    EXACT_UNIT_NAME,
    EffectError,
    EffectExecutor,
    ProcessSnapshot,
    create_approval,
    stage_plan,
)
from abyss_stack_mcp.effect_server import _run_worker, build_effect_server
from test_stack_mcp import DIGEST_C, NOW, application, observation, subject


def effect_subject() -> dict:
    payload = subject(
        "abyss-stack",
        policy_family="read",
        credential_class="abyss-stack-read",
    )
    process_identity = (
        f"systemd-user:{EXACT_UNIT_NAME}:pid:101:start:1001"
    )
    payload["process"].update(
        {
            "unit_name": EXACT_UNIT_NAME,
            "executable_ref": "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/venv/bin/python",
            "process_identity": process_identity,
        }
    )
    payload["proof"]["proved_process_identity"] = process_identity
    payload["rollback"]["last_known_good_unit_name"] = EXACT_UNIT_NAME
    payload["rollback"]["proved_target"]["unit_name"] = EXACT_UNIT_NAME
    payload["endpoint"]["endpoint_ref"] = "http://127.0.0.1:5431/mcp"
    payload["canary"]["canary_route"] = "runbook://mcp-canary/abyss-stack/read"
    payload["proof"]["proved_canary_route"] = payload["canary"]["canary_route"]
    payload["rollback"]["rollback_route"] = "runbook://mcp-rollback/abyss-stack/read"
    return payload


def prepare_effect_inputs(tmp_path: Path):
    payload = observation(effect_subject())
    app = application(tmp_path, policy_family="candidate", payload=payload)
    observation_path = tmp_path / "observation.json"
    _, digest = app.store.load()
    result = app.prepare_plan(
        "abyss-stack",
        "read",
        "restart",
        expected_observation_digest=digest,
    )
    plan = result["owner_payload"]["plan"]
    plan_path = tmp_path / "candidate-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    plan_path.chmod(0o600)
    effect_root = tmp_path / "effects"
    stage_plan(plan_path, effect_root)
    approval, _ = create_approval(
        plan_id=plan["plan_id"],
        approved_by="operator",
        idempotency_key="pilot-1",
        expires_at=NOW + timedelta(minutes=15),
        effect_root=effect_root,
        clock=lambda: NOW + timedelta(minutes=6),
    )
    return observation_path, effect_root, plan, approval


def snapshot(pid: int, started: int, minute: int) -> ProcessSnapshot:
    return ProcessSnapshot.model_validate(
        {
            "unit_name": EXACT_UNIT_NAME,
            "active_state": "active",
            "sub_state": "running",
            "main_pid": pid,
            "start_timestamp_monotonic": started,
            "process_identity": f"systemd-user:{EXACT_UNIT_NAME}:pid:{pid}:start:{started}",
            "captured_at": (NOW + timedelta(minutes=minute)).isoformat(),
        }
    )


def test_exact_approved_restart_runs_canary_and_real_rollback_once(tmp_path: Path) -> None:
    observation_path, effect_root, plan, approval = prepare_effect_inputs(tmp_path)
    snapshots = iter((snapshot(101, 1001, 6), snapshot(202, 2002, 7), snapshot(303, 3003, 8)))
    actions: list[str] = []
    canary_phases: list[str] = []

    def canary(root: Path, phase: str):
        canary_phases.append(phase)
        path = root / phase / "receipt.json"
        path.parent.mkdir(parents=True, mode=0o700)
        path.write_text('{"canary":"passed"}\n', encoding="utf-8")
        path.chmod(0o600)
        return SimpleNamespace(call_succeeded=True, result_contract_matched=True), path

    executor = EffectExecutor(
        effect_root=effect_root,
        observation_path=observation_path,
        systemctl_runner=actions.append,
        snapshot_runner=lambda: next(snapshots),
        canary_runner=canary,
        clock=lambda: NOW + timedelta(minutes=9),
    )
    receipt, replay = executor.execute(
        plan_id=plan["plan_id"],
        approval_id=approval.approval_id,
        idempotency_key="pilot-1",
    )

    assert replay is False
    assert actions == ["restart", "restart"]
    assert canary_phases == ["post-effect", "post-rollback"]
    assert receipt.outcome == "succeeded_rolled_back"
    assert receipt.deployed_tree_digest == DIGEST_C
    assert receipt.runtime_effect_authorized is True
    assert receipt.external_effect_authorized is False
    assert receipt.rollback_executed is True

    replay_receipt, replay = executor.execute(
        plan_id=plan["plan_id"],
        approval_id=approval.approval_id,
        idempotency_key="pilot-1",
    )
    assert replay is True
    assert replay_receipt.receipt_id == receipt.receipt_id
    assert actions == ["restart", "restart"]


def test_effect_start_rate_limit_denies_a_second_fresh_approval(
    tmp_path: Path,
) -> None:
    observation_path, effect_root, plan, approval = prepare_effect_inputs(tmp_path)
    second_approval, _ = create_approval(
        plan_id=plan["plan_id"],
        approved_by="operator",
        idempotency_key="pilot-2",
        expires_at=NOW + timedelta(minutes=15),
        effect_root=effect_root,
        clock=lambda: NOW + timedelta(minutes=6),
    )
    snapshots = iter(
        (snapshot(101, 1001, 6), snapshot(202, 2002, 7), snapshot(303, 3003, 8))
    )
    actions: list[str] = []

    def canary(root: Path, phase: str):
        path = root / phase / "receipt.json"
        path.parent.mkdir(parents=True, mode=0o700)
        path.write_text('{"canary":"passed"}\n', encoding="utf-8")
        path.chmod(0o600)
        return SimpleNamespace(call_succeeded=True, result_contract_matched=True), path

    executor = EffectExecutor(
        effect_root=effect_root,
        observation_path=observation_path,
        systemctl_runner=actions.append,
        snapshot_runner=lambda: next(snapshots),
        canary_runner=canary,
        clock=lambda: NOW + timedelta(minutes=9),
    )
    executor.execute(
        plan_id=plan["plan_id"],
        approval_id=approval.approval_id,
        idempotency_key="pilot-1",
    )
    with pytest.raises(EffectError, match="start rate limit exceeded"):
        executor.execute(
            plan_id=plan["plan_id"],
            approval_id=second_approval.approval_id,
            idempotency_key="pilot-2",
        )
    assert actions == ["restart", "restart"]
    denials = list((effect_root / "denial-receipts").glob("*.json"))
    assert len(denials) == 1
    assert json.loads(denials[0].read_text())["reason_code"] == (
        "internal_effect_start_rate_limit_exceeded"
    )


def test_expired_approval_denies_before_any_effect(tmp_path: Path) -> None:
    observation_path, effect_root, plan, approval = prepare_effect_inputs(tmp_path)
    actions: list[str] = []
    executor = EffectExecutor(
        effect_root=effect_root,
        observation_path=observation_path,
        systemctl_runner=actions.append,
        snapshot_runner=lambda: snapshot(101, 1001, 6),
        clock=lambda: NOW + timedelta(minutes=16),
    )
    with pytest.raises(EffectError, match="approval does not authorize"):
        executor.execute(
            plan_id=plan["plan_id"],
            approval_id=approval.approval_id,
            idempotency_key="pilot-1",
        )
    assert actions == []
    denial = list((effect_root / "denial-receipts").glob("*.json"))
    assert len(denial) == 1
    denial_payload = json.loads(denial[0].read_text())
    assert denial_payload["effect_attempted"] is False
    assert denial_payload["runtime_effect_authorized"] is False
    assert "pilot-1" not in denial[0].read_text()


def test_observation_drift_denies_before_any_effect(tmp_path: Path) -> None:
    observation_path, effect_root, plan, approval = prepare_effect_inputs(tmp_path)
    payload = json.loads(observation_path.read_text(encoding="utf-8"))
    payload["provider_watermark"] = "drifted-watermark"
    observation_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    actions: list[str] = []
    executor = EffectExecutor(
        effect_root=effect_root,
        observation_path=observation_path,
        systemctl_runner=actions.append,
        snapshot_runner=lambda: snapshot(101, 1001, 6),
        clock=lambda: NOW + timedelta(minutes=9),
    )
    with pytest.raises(EffectError, match="observation drift"):
        executor.execute(
            plan_id=plan["plan_id"],
            approval_id=approval.approval_id,
            idempotency_key="pilot-1",
        )
    assert actions == []
    denial = list((effect_root / "denial-receipts").glob("*.json"))
    assert len(denial) == 1
    assert json.loads(denial[0].read_text())["reason_code"] == (
        "runtime_observation_drift_blocks_execution"
    )


def test_failed_post_effect_canary_still_executes_and_verifies_rollback(tmp_path: Path) -> None:
    observation_path, effect_root, plan, approval = prepare_effect_inputs(tmp_path)
    snapshots = iter((snapshot(101, 1001, 6), snapshot(202, 2002, 7), snapshot(303, 3003, 8)))
    actions: list[str] = []

    def canary(root: Path, phase: str):
        if phase == "post-effect":
            raise EffectError("synthetic post-effect failure")
        path = root / phase / "receipt.json"
        path.parent.mkdir(parents=True, mode=0o700)
        path.write_text('{"canary":"passed"}\n', encoding="utf-8")
        path.chmod(0o600)
        return SimpleNamespace(call_succeeded=True, result_contract_matched=True), path

    executor = EffectExecutor(
        effect_root=effect_root,
        observation_path=observation_path,
        systemctl_runner=actions.append,
        snapshot_runner=lambda: next(snapshots),
        canary_runner=canary,
        clock=lambda: NOW + timedelta(minutes=9),
    )
    with pytest.raises(EffectError, match="successful automatic rollback"):
        executor.execute(
            plan_id=plan["plan_id"],
            approval_id=approval.approval_id,
            idempotency_key="pilot-1",
        )
    assert actions == ["restart", "restart"]
    recovery = list((effect_root / "recovery-receipts").glob("*.json"))
    assert len(recovery) == 1
    assert json.loads(recovery[0].read_text())["rollback_succeeded"] is True


def test_failed_rollback_is_persisted_without_false_success(tmp_path: Path) -> None:
    observation_path, effect_root, plan, approval = prepare_effect_inputs(tmp_path)
    snapshots = iter((snapshot(101, 1001, 6), snapshot(202, 2002, 7)))
    actions: list[str] = []

    def restart(action: str) -> None:
        actions.append(action)
        if len(actions) == 2:
            raise EffectError("synthetic rollback restart failure")

    def canary(root: Path, phase: str):
        path = root / phase / "receipt.json"
        path.parent.mkdir(parents=True, mode=0o700)
        path.write_text('{"canary":"passed"}\n', encoding="utf-8")
        path.chmod(0o600)
        return SimpleNamespace(call_succeeded=True, result_contract_matched=True), path

    executor = EffectExecutor(
        effect_root=effect_root,
        observation_path=observation_path,
        systemctl_runner=restart,
        snapshot_runner=lambda: next(snapshots),
        canary_runner=canary,
        clock=lambda: NOW + timedelta(minutes=9),
    )
    with pytest.raises(EffectError, match="rollback was not proved"):
        executor.execute(
            plan_id=plan["plan_id"],
            approval_id=approval.approval_id,
            idempotency_key="pilot-1",
        )
    assert actions == ["restart", "restart"]
    recovery = list((effect_root / "recovery-receipts").glob("*.json"))
    assert len(recovery) == 1
    payload = json.loads(recovery[0].read_text())
    assert payload["rollback_succeeded"] is False
    assert payload["outcome"] == "effect_failed_rollback_failed"
    assert payload["post_rollback"] is None
    assert list((effect_root / "denial-receipts").glob("*.json")) == []


def test_effect_server_exposes_only_the_exact_pilot_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AOA_MCP_TRANSPORT", "stdio")
    monkeypatch.delenv("ABYSS_STACK_MCP_REQUIRE_AUTH_MANIFEST", raising=False)
    server = build_effect_server()
    tools = asyncio.run(server.list_tools())
    assert [tool.name for tool in tools] == [
        "stack_execute_approved_read_restart_pilot"
    ]
    tool = tools[0]
    assert tool.annotations.destructiveHint is True
    assert tool.annotations.idempotentHint is True
    assert set(tool.inputSchema["properties"]) == {
        "plan_id",
        "approval_id",
        "idempotency_key",
    }


def test_caller_cancellation_waits_for_bounded_worker_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 424242
        returncode: int | None = None

        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.wait_called = False

        async def communicate(self):
            self.started.set()
            await self.release.wait()
            return b"", b""

        async def wait(self):
            self.wait_called = True
            self.returncode = 0
            return 0

    process = FakeProcess()

    async def create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)

    async def scenario() -> None:
        task = asyncio.create_task(
            _run_worker(
                plan_id="sha256:" + "a" * 64,
                approval_id="sha256:" + "b" * 64,
                idempotency_key="pilot-cancel",
                effect_root=tmp_path / "effects",
                observation_path=tmp_path / "observation.json",
            )
        )
        await process.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert process.wait_called is True


def test_worker_timeout_terminates_only_its_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 434343
        returncode: int | None = None

        async def communicate(self):
            await asyncio.Event().wait()

        async def wait(self):
            self.returncode = -15
            return -15

    process = FakeProcess()
    killed: list[tuple[int, int]] = []

    async def create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)
    monkeypatch.setattr(effect_server_module, "WORKER_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(effect_server_module.os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    with pytest.raises(EffectError, match="exceeded its bounded timeout"):
        asyncio.run(
            _run_worker(
                plan_id="sha256:" + "a" * 64,
                approval_id="sha256:" + "b" * 64,
                idempotency_key="pilot-timeout",
                effect_root=tmp_path / "effects",
                observation_path=tmp_path / "observation.json",
            )
        )
    assert killed == [(process.pid, effect_server_module.signal.SIGTERM)]
