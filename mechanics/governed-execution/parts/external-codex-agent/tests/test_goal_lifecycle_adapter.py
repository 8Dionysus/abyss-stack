from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aoa_sdk.contracts.control_plane import ContentRef, ProvenanceRef
from aoa_sdk.contracts.goal_lifecycle import (
    GoalLifecycleContext,
    GoalLifecycleRequest,
    GoalLifecycleTransition,
    resolve_goal_lifecycle,
)


PART = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RUNTIME = _load("external_codex_return", PART / "external_codex_return.py")
ADAPTER = _load("goal_lifecycle_adapter", PART / "goal_lifecycle_adapter.py")
REAL_SEMANTIC_ATTEMPT_STATE_ROOT = ADAPTER._semantic_attempt_state_root


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolated_semantic_attempt_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_root = tmp_path / "semantic-attempt-locks"
    goal_lock_root = tmp_path / "goal-identity-locks"
    state_root = tmp_path / "semantic-attempt-state"
    lock_root.mkdir(mode=0o700)
    goal_lock_root.mkdir(mode=0o700)
    state_root.mkdir(mode=0o700)
    monkeypatch.setattr(ADAPTER, "_semantic_attempt_lock_root", lambda: lock_root)
    monkeypatch.setattr(ADAPTER, "_semantic_attempt_state_root", lambda: state_root)
    monkeypatch.setattr(RUNTIME, "_pause_attempt_lock_root", lambda: goal_lock_root)


def test_semantic_state_root_creates_each_parent_owner_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setattr(
        ADAPTER.pwd,
        "getpwuid",
        lambda _uid: SimpleNamespace(pw_dir=str(home)),
    )
    previous_umask = os.umask(0o002)
    try:
        root = REAL_SEMANTIC_ATTEMPT_STATE_ROOT()
    finally:
        os.umask(previous_umask)

    assert root == home / ".local" / "state" / "aoa-external-codex" / "goal-lifecycle"
    for directory in (
        home / ".local",
        home / ".local" / "state",
        home / ".local" / "state" / "aoa-external-codex",
        root,
    ):
        assert directory.stat().st_mode & 0o777 == 0o700


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _provenance(owner: str, artifact: str) -> ProvenanceRef:
    return ProvenanceRef(
        owner_repo=owner,
        artifact_ref=artifact,
        source_ref="goal-lifecycle-adapter-test",
        artifact_digest=_digest([owner, artifact]),
        schema_ref="goal-lifecycle-adapter-test",
        schema_version="v1",
    )


def _ref(object_id: str, owner: str = "codex-goal") -> ContentRef:
    return ContentRef(
        object_id=object_id,
        owner_repo=owner,
        schema_version="v1",
        digest=_digest(object_id),
    )


def _owner(endpoint: Path | None = None) -> dict[str, Any]:
    owner = {
        "schema_version": RUNTIME.GOAL_LIFECYCLE_OWNER_SCHEMA_VERSION,
        "owner_id": "holder:master:test",
        "owner_repo": "codex-goal",
        "goal_id": "goal:test",
        "thread_id": "thread:test",
        "goal_ref": _ref("goal:test").model_dump(mode="json"),
        "return_owner_ref": _ref("holder:master:test").model_dump(mode="json"),
        "runtime": "codex",
        "transport_posture": "explicit-endpoint",
        "acceptance_posture": "owner-return-pending",
    }
    if endpoint is not None:
        owner["transport_endpoint"] = str(endpoint)
    return owner


def _request(*, observed: str, desired: str, kind: str, request_id: str) -> GoalLifecycleRequest:
    evidence = _provenance("aoa-agents", f"evidence/{kind}")
    return GoalLifecycleRequest(
        request_id=request_id,
        correlation_id="goal-lifecycle-correlation:test",
        idempotency_key=f"idempotency:{request_id}",
        goal_ref=_ref("goal:test"),
        observed_state=observed,
        expected_state=observed,
        desired_state=desired,
        transition_kind=kind,
        reason=f"owner-admitted {kind}",
        evidence_refs=(evidence,),
        current_holder_ref=_ref("holder:master:test"),
        return_owner_ref=_ref("holder:master:test"),
        requested_by=_provenance("codex-goal", "holder/master"),
        requested_at=NOW,
    )


def _decision(request: GoalLifecycleRequest):
    context = GoalLifecycleContext(
        context_id=f"context:{request.request_id}",
        correlation_id=request.correlation_id,
        goal_ref=request.goal_ref,
        observed_state=request.observed_state,
        dag_ref=_ref("dag:test", "aoa-skills"),
        ownership_ref=_ref("ownership:test", "aoa-agents"),
        current_holder_ref=request.current_holder_ref,
        return_owner_ref=request.return_owner_ref,
        allowed_transitions=(
            GoalLifecycleTransition(
                from_state=request.observed_state,
                to_state=request.desired_state,
                transition_kind=request.transition_kind,
            ),
        ),
        evidence_refs=request.evidence_refs,
        observed_at=NOW,
        valid_until=datetime(2099, 1, 1, tzinfo=timezone.utc),
        observed_by=_provenance("aoa-agents", "context/goal-dag-ownership"),
    )
    return resolve_goal_lifecycle(request, context)


class FakeGoalRpc:
    def __init__(self, endpoint: Path, *, status: str) -> None:
        self.endpoint = endpoint
        self.status = status
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self.counter = 0
        self.mutation_response_extra: dict[str, object] = {}
        self.goal_get_extra: dict[str, object] = {}
        self.lose_goal_set_response = False

    def __enter__(self) -> "FakeGoalRpc":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def notify(self, method: str, params: dict[str, object] | None = None) -> None:
        self.calls.append((method, params))

    def call(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.counter += 1
        self.calls.append((method, params))
        if method == "initialize":
            return {"protocolVersion": "1"}
        if method == "thread/goal/get":
            response: dict[str, object] = {
                "goal": {"threadId": "thread:test", "status": self.status}
            }
            response.update(self.goal_get_extra)
            return response
        if method == "thread/goal/set":
            assert isinstance(params, dict)
            request_id = self.counter
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            prepare_callback = getattr(self, "request_prepare_callback", None)
            if callable(prepare_callback):
                prepare_callback(method, params, request_id, payload)
            issued_callback = getattr(self, "request_issued_callback", None)
            if callable(issued_callback):
                issued_callback(method, params, request_id, payload)
            self.status = str(params["status"])
            response: dict[str, object] = {
                "goal": {"threadId": "thread:test", "status": self.status}
            }
            response.update(self.mutation_response_extra)
            if self.lose_goal_set_response:
                raise RUNTIME.ExternalCodexReturnError(
                    "simulated Goal set response loss"
                )
            return response
        raise AssertionError(f"unexpected non-lifecycle method: {method}")


def _run_transition(tmp_path: Path, *, initial: str, desired: str, kind: str) -> tuple[dict[str, Any], FakeGoalRpc]:
    endpoint = tmp_path / f"{kind}.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / f"owner-{kind}.json"
    owner_path.write_text(json.dumps(owner), encoding="utf-8")
    rpc = FakeGoalRpc(endpoint, status=initial)
    request = _request(
        observed=initial,
        desired=desired,
        kind=kind,
        request_id=f"request:{kind}",
    )
    decision = _decision(request)
    receipt = ADAPTER.execute_goal_transition(
        request,
        decision,
        owner,
        owner_path,
        endpoint,
        rpc_factory=lambda _endpoint: rpc,
        attempt_path=tmp_path / f"{kind}.attempt.json",
    )
    return receipt, rpc


def _cli_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    request_id: str,
) -> tuple[SimpleNamespace, Path, Path, Path, FakeGoalRpc]:
    endpoint = tmp_path / "cli.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner.json"
    request_path = tmp_path / "request.json"
    decision_path = tmp_path / "decision.json"
    receipt_path = tmp_path / "receipt.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id=request_id,
    )
    decision = _decision(request)
    request_path.write_bytes(
        RUNTIME._canonical_bytes(request.model_dump(mode="json")) + b"\n"
    )
    decision_path.write_bytes(
        RUNTIME._canonical_bytes(decision.model_dump(mode="json")) + b"\n"
    )
    rpc = FakeGoalRpc(endpoint, status="active")
    monkeypatch.setattr(
        RUNTIME,
        "discover_app_server_socket",
        lambda _owner, **_kwargs: (rpc.endpoint, "test-fixture"),
    )
    monkeypatch.setattr(RUNTIME, "UnixWebSocketRpc", lambda _endpoint: rpc)
    args = SimpleNamespace(
        request=str(request_path),
        decision=str(decision_path),
        owner=str(owner_path),
        receipt=str(receipt_path),
    )
    return args, request_path, decision_path, receipt_path, rpc


def test_generic_adapter_cli_validates_owner_scope_before_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _request_path, _decision_path, _receipt_path, rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:owner-before-discovery"
    )
    owner_path = Path(args.owner)
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    owner["goal_ref"]["digest"] = _digest("different-goal-authority")
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")

    def fail_discovery(_owner: dict[str, Any], **_kwargs: object) -> tuple[Path, str]:
        raise AssertionError("transport opened")

    monkeypatch.setattr(RUNTIME, "discover_app_server_socket", fail_discovery)
    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="Goal reference mismatch",
    ):
        ADAPTER.run_goal_transition(args)
    assert rpc.calls == []


def test_generic_adapter_executes_pause_and_confirms_authoritative_goal_read(tmp_path: Path) -> None:
    receipt, rpc = _run_transition(
        tmp_path, initial="active", desired="paused", kind="delegation_yield"
    )

    assert receipt["status"] == "executed"
    assert receipt["resulting_state"] == "paused"
    assert receipt["boundaries"] == {
        "requested": True,
        "accepted": True,
        "executed": True,
        "delivered": False,
        "semantically_accepted": False,
        "closed": False,
    }
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1
    assert [method for method, _params in rpc.calls].count("thread/goal/get") == 2
    assert all("turn" not in method for method, _params in rpc.calls)


def test_generic_adapter_reuses_the_same_seam_for_return_activation(tmp_path: Path) -> None:
    receipt, rpc = _run_transition(
        tmp_path, initial="paused", desired="active", kind="accepted_return"
    )

    assert receipt["status"] == "executed"
    assert receipt["desired_state"] == "active"
    assert receipt["transport"]["method"] == "thread/goal/set"
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


def test_generic_adapter_replays_an_already_desired_state_read_only(tmp_path: Path) -> None:
    receipt, rpc = _run_transition(
        tmp_path, initial="active", desired="active", kind="accepted_return"
    )

    assert receipt["status"] == "replayed"
    assert receipt["transport"]["method"] == "thread/goal/get"
    attempt_path = tmp_path / "accepted_return.attempt.json"
    assert receipt["attempt_artifact"]["ref"] == str(attempt_path.resolve())
    assert json.loads(attempt_path.read_text(encoding="utf-8"))["state"] == (
        "read_only_recorded"
    )
    assert [method for method, _params in rpc.calls].count("thread/goal/get") == 1
    assert not any(method == "thread/goal/set" for method, _params in rpc.calls)


def test_generic_adapter_rejects_pathless_read_only_completion(
    tmp_path: Path,
) -> None:
    endpoint = tmp_path / "pathless-read-only.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner-pathless-read-only.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:pathless-read-only",
    )
    decision = _decision(request)
    rpc = FakeGoalRpc(endpoint, status="paused")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="requires a durable attempt path",
    ):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
        )

    assert rpc.calls == []


def test_generic_adapter_binds_receipt_transition_evidence_to_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _request_path, _decision_path, receipt_path, rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:receipt-attempt-binding"
    )
    ADAPTER.run_goal_transition(args)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    lifecycle = receipt["lifecycle"]
    tampered_request = dict(lifecycle["transition_request"])
    tampered_request["id"] += 1
    tampered_proof = dict(lifecycle["transition_proof"])
    tampered_proof["request_id"] = tampered_request["id"]
    tampered_proof["request_sha256"] = _digest(tampered_request)
    lifecycle["transition_request"] = tampered_request
    lifecycle["transition_proof"] = tampered_proof
    receipt_path.write_bytes(RUNTIME._canonical_bytes(receipt) + b"\n")
    before_calls = list(rpc.calls)

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="does not match its attempt",
    ):
        ADAPTER.run_goal_transition(args)
    assert rpc.calls == before_calls


def test_generic_adapter_binds_read_only_receipt_to_attempt_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, request_path, decision_path, receipt_path, rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:read-only-receipt-binding"
    )
    request = _request(
        observed="active",
        desired="active",
        kind="accepted_return",
        request_id="request:read-only-receipt-binding",
    )
    decision = _decision(request)
    request_path.write_bytes(
        RUNTIME._canonical_bytes(request.model_dump(mode="json")) + b"\n"
    )
    decision_path.write_bytes(
        RUNTIME._canonical_bytes(decision.model_dump(mode="json")) + b"\n"
    )
    ADAPTER.run_goal_transition(args)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    tampered_read = {
        "goal": {"threadId": "thread:test", "status": "active"},
        "server_metadata": {"revision": 99},
    }
    receipt["lifecycle"]["result"] = RUNTIME._safe_response_summary(tampered_read)
    receipt["lifecycle"]["result_response"] = tampered_read
    receipt["lifecycle"]["result_response_sha256"] = _digest(tampered_read)
    receipt_path.write_bytes(RUNTIME._canonical_bytes(receipt) + b"\n")
    before_calls = list(rpc.calls)

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="read-only evidence does not match its attempt",
    ):
        ADAPTER.run_goal_transition(args)
    assert rpc.calls == before_calls


def test_generic_adapter_cli_route_replays_canonical_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _request_path, _decision_path, receipt_path, rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:cli"
    )
    rpc.mutation_response_extra = {"set_response_only": True}

    first = ADAPTER.run_goal_transition(args)
    rpc.goal_get_extra = {"server_metadata": {"revision": 2}}
    second = ADAPTER.run_goal_transition(args)

    assert first == second
    assert first["receipt_ref"] == str(receipt_path.resolve())
    assert first["transport"]["resolution"] == "test-fixture"
    assert (
        first["lifecycle"]["mutation_response_sha256"]
        == _digest(
            {
                "goal": {"threadId": "thread:test", "status": "paused"},
                "set_response_only": True,
            }
        )
    )
    assert first["lifecycle"]["result_response_sha256"] == _digest(
        {"goal": {"threadId": "thread:test", "status": "paused"}}
    )
    assert first["lifecycle"]["result_response"] == {
        "goal": {"threadId": "thread:test", "status": "paused"}
    }
    assert (
        first["lifecycle"]["mutation_response_sha256"]
        != first["lifecycle"]["result_response_sha256"]
    )
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


def test_generic_adapter_rejects_a_tampered_recovery_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _request_path, _decision_path, receipt_path, rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:recovery-summary"
    )
    rpc.lose_goal_set_response = True
    with pytest.raises(RUNTIME.ExternalCodexReturnError, match="response loss"):
        ADAPTER.run_goal_transition(args)

    rpc.lose_goal_set_response = False
    ADAPTER.run_goal_transition(args)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["lifecycle"]["recovery"]["authoritative"]["keys"] = ["tampered"]
    receipt_path.write_bytes(RUNTIME._canonical_bytes(receipt) + b"\n")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="recovery evidence",
    ):
        ADAPTER.run_goal_transition(args)


def test_generic_adapter_validates_stored_goal_identity_and_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _request_path, _decision_path, receipt_path, rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:stored-goal-binding"
    )
    ADAPTER.run_goal_transition(args)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    attempt_path = receipt_path.with_name(receipt_path.name + ".attempt.json")
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))

    tampered_post_read = {
        "goal": {"threadId": "thread:other", "status": "paused"}
    }
    attempt["post_read_response"] = tampered_post_read
    attempt["transition_proof"]["post_read_response_sha256"] = _digest(
        tampered_post_read
    )
    attempt_raw = RUNTIME._canonical_bytes(attempt) + b"\n"
    attempt_path.write_bytes(attempt_raw)
    receipt["attempt_artifact"]["sha256"] = RUNTIME._sha256_bytes(attempt_raw)
    receipt["lifecycle"]["result"] = RUNTIME._safe_response_summary(
        tampered_post_read
    )
    receipt["lifecycle"]["result_response"] = tampered_post_read
    receipt["lifecycle"]["result_response_sha256"] = _digest(tampered_post_read)
    receipt["lifecycle"]["transition_proof"] = attempt["transition_proof"]
    receipt_path.write_bytes(RUNTIME._canonical_bytes(receipt) + b"\n")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="different thread",
    ):
        ADAPTER.run_goal_transition(args)


def test_generic_adapter_validates_stored_precondition_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _request_path, _decision_path, receipt_path, _rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:stored-precondition-state"
    )
    ADAPTER.run_goal_transition(args)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    attempt_path = receipt_path.with_name(receipt_path.name + ".attempt.json")
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))

    tampered_precondition_response = {
        "goal": {"threadId": "thread:test", "status": "paused"}
    }
    tampered_precondition_summary = RUNTIME._safe_response_summary(
        tampered_precondition_response
    )
    attempt["precondition"]["goal_get_response"] = tampered_precondition_response
    attempt["precondition"]["goal_get"] = tampered_precondition_summary
    attempt["precondition"]["goal_get_summary_sha256"] = _digest(
        tampered_precondition_summary
    )
    attempt["precondition"]["goal_response_sha256"] = _digest(
        tampered_precondition_response
    )
    attempt["transition_proof"]["precondition_sha256"] = _digest(
        tampered_precondition_response
    )
    attempt_raw = RUNTIME._canonical_bytes(attempt) + b"\n"
    attempt_path.write_bytes(attempt_raw)
    receipt["attempt_artifact"]["sha256"] = RUNTIME._sha256_bytes(attempt_raw)
    receipt["lifecycle"]["before"] = tampered_precondition_summary
    receipt["lifecycle"]["before_response_sha256"] = _digest(
        tampered_precondition_response
    )
    receipt["lifecycle"]["transition_proof"] = attempt["transition_proof"]
    receipt_path.write_bytes(RUNTIME._canonical_bytes(receipt) + b"\n")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="state 'active'",
    ):
        ADAPTER.run_goal_transition(args)


def test_generic_adapter_requires_attempt_artifact_on_executed_receipt_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _request_path, _decision_path, receipt_path, _rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:attempt-required"
    )
    ADAPTER.run_goal_transition(args)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("attempt_artifact")
    receipt_path.write_bytes(RUNTIME._canonical_bytes(receipt) + b"\n")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="requires a mutation attempt artifact",
    ):
        ADAPTER.run_goal_transition(args)


def test_generic_adapter_binds_authoritative_result_on_receipt_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _request_path, _decision_path, receipt_path, _rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:result-evidence"
    )
    ADAPTER.run_goal_transition(args)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["lifecycle"]["result"]["goal"]["status"] = "active"
    receipt_path.write_bytes(RUNTIME._canonical_bytes(receipt) + b"\n")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="authoritative result evidence is not bound",
    ):
        ADAPTER.run_goal_transition(args)


def test_generic_adapter_requires_canonical_receipt_path_on_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _request_path, _decision_path, receipt_path, _rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:receipt-path"
    )
    ADAPTER.run_goal_transition(args)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("receipt_ref")
    receipt_path.write_bytes(RUNTIME._canonical_bytes(receipt) + b"\n")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError, match="receipt path identity mismatch"
    ):
        ADAPTER.run_goal_transition(args)


def test_generic_adapter_rejects_attempt_sidecar_input_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _owner()
    owner_path = tmp_path / "owner.json"
    decision_path = tmp_path / "decision.json"
    receipt_path = tmp_path / "receipt.json"
    attempt_path = Path(f"{receipt_path}.attempt.json")
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:attempt-alias",
    )
    decision = _decision(request)
    attempt_path.write_bytes(
        RUNTIME._canonical_bytes(request.model_dump(mode="json")) + b"\n"
    )
    decision_path.write_bytes(
        RUNTIME._canonical_bytes(decision.model_dump(mode="json")) + b"\n"
    )
    rpc = FakeGoalRpc(tmp_path / "alias.sock", status="active")

    def fail_discovery(_owner: dict[str, Any]) -> tuple[Path, str]:
        raise AssertionError("transport opened")

    monkeypatch.setattr(RUNTIME, "discover_app_server_socket", fail_discovery)
    args = SimpleNamespace(
        request=str(attempt_path),
        decision=str(decision_path),
        owner=str(owner_path),
        receipt=str(receipt_path),
    )

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="distinct from all input artifacts",
    ):
        ADAPTER.run_goal_transition(args)
    assert rpc.calls == []


def test_generic_adapter_binds_complete_owner_qualified_references(
    tmp_path: Path,
) -> None:
    owner = _owner()
    owner_path = tmp_path / "owner.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    endpoint = tmp_path / "owner-ref.sock"
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:owner-ref",
    ).model_copy(update={"goal_ref": _ref("goal:test", "different-owner")})
    decision = _decision(request)
    rpc = FakeGoalRpc(endpoint, status="active")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="Goal reference mismatch",
    ):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=tmp_path / "owner-ref.attempt.json",
        )
    assert rpc.calls == []


def test_generic_adapter_rejects_owner_path_projection_split(
    tmp_path: Path,
) -> None:
    owner = _owner()
    owner_path = tmp_path / "owner.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    supplied_owner = owner.copy()
    supplied_owner["acceptance_posture"] = "different-owner-projection"
    endpoint = tmp_path / "owner-projection.sock"
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:owner-projection",
    )
    decision = _decision(request)
    rpc = FakeGoalRpc(endpoint, status="active")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="owner artifact does not match the supplied owner",
    ):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            supplied_owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=tmp_path / "owner-projection.attempt.json",
        )
    assert rpc.calls == []


def test_generic_adapter_binds_supplied_endpoint_before_opening_transport(
    tmp_path: Path,
) -> None:
    owner = _owner()
    owner_path = tmp_path / "owner.json"
    owner_endpoint = tmp_path / "owner-bound.sock"
    supplied_endpoint = tmp_path / "unrelated.sock"
    owner["transport_endpoint"] = str(owner_endpoint)
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:endpoint-binding",
    )
    decision = _decision(request)
    rpc = FakeGoalRpc(supplied_endpoint, status="active")
    opened: list[Path] = []

    def factory(endpoint: Path) -> FakeGoalRpc:
        opened.append(endpoint)
        return rpc

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="does not match the owner-bound endpoint",
    ):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            supplied_endpoint,
            rpc_factory=factory,
            attempt_path=tmp_path / "endpoint-binding.attempt.json",
        )

    assert opened == []
    assert rpc.calls == []


def test_generic_adapter_loads_existing_attempt_before_replacing_it(
    tmp_path: Path,
) -> None:
    owner_path = tmp_path / "owner.json"
    endpoint = tmp_path / "existing-attempt.sock"
    owner = _owner(endpoint)
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    attempt_path = tmp_path / "existing-attempt.json"
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:existing-attempt",
    )
    decision = _decision(request)
    goal_response = {
        "goal": {"threadId": "thread:test", "status": "active"}
    }
    content_ref_type, _decision_type, _execution_type, _request_type, _scope, _assert_receipt_scope, canonical_digest = ADAPTER._contract_types()
    attempt = ADAPTER._attempt_binding(
        request=request,
        decision=decision,
        owner=owner,
        owner_path=owner_path,
        owner_bytes=owner_path.read_bytes(),
        endpoint=endpoint,
        attempt_path=attempt_path,
        precondition=ADAPTER._precondition(goal_response, "active"),
        content_ref_type=content_ref_type,
        canonical_digest=canonical_digest,
    )
    attempt_path.write_bytes(RUNTIME._canonical_bytes(attempt) + b"\n")
    before = attempt_path.read_bytes()
    rpc = FakeGoalRpc(endpoint, status="active")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="already has a durable attempt",
    ):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=attempt_path,
        )

    assert attempt_path.read_bytes() == before
    assert not any(method == "thread/goal/set" for method, _params in rpc.calls)


@pytest.mark.parametrize(
    ("reference_key", "reference_id", "owner_key"),
    (
        ("goal_ref", "goal:other", "goal_id"),
        ("return_owner_ref", "holder:other", "owner_id"),
    ),
)
def test_generic_owner_binds_reference_object_ids_to_owner_ids(
    reference_key: str, reference_id: str, owner_key: str
) -> None:
    owner = _owner()
    owner[reference_key] = _ref(reference_id).model_dump(mode="json")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match=rf"reference object_id must match {owner_key}",
    ):
        RUNTIME.validate_goal_lifecycle_owner(owner)


@pytest.mark.parametrize("reference_key", ("goal_ref", "return_owner_ref"))
def test_generic_owner_binds_reference_repositories_to_owner_repository(
    reference_key: str,
) -> None:
    owner = _owner()
    reference = owner[reference_key].copy()
    reference["owner_repo"] = "unrelated-owner"
    owner[reference_key] = reference

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="reference owner_repo must match owner_repo",
    ):
        RUNTIME.validate_goal_lifecycle_owner(owner)


def test_generic_adapter_rejects_recovery_under_a_different_decision(
    tmp_path: Path,
) -> None:
    owner_path = tmp_path / "owner.json"
    endpoint = tmp_path / "decision-recovery.sock"
    owner = _owner(endpoint)
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    attempt_path = tmp_path / "decision-recovery.attempt.json"
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:decision-recovery",
    )
    decision = _decision(request)
    rpc = FakeGoalRpc(endpoint, status="active")
    ADAPTER.execute_goal_transition(
        request,
        decision,
        owner,
        owner_path,
        endpoint,
        rpc_factory=lambda _endpoint: rpc,
        attempt_path=attempt_path,
    )
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    alternate_decision = decision.model_copy(update={"decision_id": "decision:alternate"})

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="attempt reservation is outside request/owner scope",
    ):
        ADAPTER.execute_goal_transition(
            request,
            alternate_decision,
            owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=attempt_path,
            attempt=attempt,
        )
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


@pytest.mark.parametrize("durable_state", ("missing", "mismatched"))
def test_generic_adapter_requires_supplied_attempt_to_match_durable_artifact(
    tmp_path: Path,
    durable_state: str,
) -> None:
    endpoint = tmp_path / f"supplied-attempt-{durable_state}.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / f"owner-supplied-attempt-{durable_state}.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id=f"request:supplied-attempt-{durable_state}",
    )
    decision = _decision(request)
    attempt_path = tmp_path / f"supplied-attempt-{durable_state}.attempt.json"
    content_ref_type, _decision_type, _execution_type, _request_type, _scope, _assert_receipt_scope, canonical_digest = ADAPTER._contract_types()
    attempt = ADAPTER._attempt_binding(
        request=request,
        decision=decision,
        owner=owner,
        owner_path=owner_path,
        owner_bytes=owner_path.read_bytes(),
        endpoint=endpoint,
        attempt_path=attempt_path,
        precondition=ADAPTER._precondition(
            {"goal": {"threadId": owner["thread_id"], "status": "active"}},
            "active",
        ),
        content_ref_type=content_ref_type,
        canonical_digest=canonical_digest,
    )
    if durable_state == "mismatched":
        mismatched = {**attempt, "correlation_id": "different-correlation"}
        attempt_path.write_bytes(RUNTIME._canonical_bytes(mismatched) + b"\n")
    rpc = FakeGoalRpc(endpoint, status="active")

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match=(
            "requires its durable artifact"
            if durable_state == "missing"
            else "does not match its durable artifact"
        ),
    ):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=attempt_path,
            attempt=attempt,
        )

    assert rpc.calls == []


def test_generic_adapter_rechecks_all_inputs_before_publishing_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _owner()
    owner_path = tmp_path / "owner.json"
    request_path = tmp_path / "request.json"
    decision_path = tmp_path / "decision.json"
    receipt_path = tmp_path / "receipt.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:publication-snapshot",
    )
    decision = _decision(request)
    request_bytes = RUNTIME._canonical_bytes(request.model_dump(mode="json")) + b"\n"
    decision_bytes = RUNTIME._canonical_bytes(decision.model_dump(mode="json")) + b"\n"
    request_path.write_bytes(request_bytes)
    decision_path.write_bytes(decision_bytes)
    rpc = FakeGoalRpc(tmp_path / "publication-snapshot.sock", status="active")
    original_call = rpc.call

    def mutate_request_after_mutation(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        result = original_call(method, params)
        if method == "thread/goal/set":
            request_path.write_bytes(b"{}\n")
        return result

    rpc.call = mutate_request_after_mutation  # type: ignore[method-assign]
    monkeypatch.setattr(
        RUNTIME,
        "discover_app_server_socket",
        lambda _owner, **_kwargs: (rpc.endpoint, "test-fixture"),
    )
    monkeypatch.setattr(RUNTIME, "UnixWebSocketRpc", lambda _endpoint: rpc)
    args = SimpleNamespace(
        request=str(request_path),
        decision=str(decision_path),
        owner=str(owner_path),
        receipt=str(receipt_path),
    )

    with pytest.raises(RUNTIME.VISIBLE.IncarnationHomeError, match="changed during validation"):
        ADAPTER.run_goal_transition(args)
    assert not receipt_path.exists()


@pytest.mark.parametrize("artifact_name", ("request", "decision"))
def test_cli_rechecks_authority_artifacts_after_receipt_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_name: str,
) -> None:
    args, request_path, decision_path, receipt_path, _rpc = _cli_fixture(
        tmp_path,
        monkeypatch,
        request_id=f"request:{artifact_name}-drift-after-publication",
    )
    target = request_path if artifact_name == "request" else decision_path
    original_replace_json = RUNTIME._replace_json

    def replace_then_drift(path: Path, value: object, label: str) -> None:
        original_replace_json(path, value, label)
        if label == "Goal lifecycle receipt":
            target.write_bytes(b"{}\n")

    monkeypatch.setattr(RUNTIME, "_replace_json", replace_then_drift)
    with pytest.raises(
        RUNTIME.VISIBLE.IncarnationHomeError,
        match="changed during validation",
    ):
        ADAPTER.run_goal_transition(args)
    assert receipt_path.exists()


@pytest.mark.parametrize("artifact_name", ("request", "decision"))
def test_cli_rechecks_authority_artifacts_immediately_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_name: str,
) -> None:
    args, request_path, decision_path, receipt_path, rpc = _cli_fixture(
        tmp_path,
        monkeypatch,
        request_id=f"request:{artifact_name}-drift-before-mutation",
    )
    target = request_path if artifact_name == "request" else decision_path
    original_call = rpc.call
    drifted = False

    def mutate_after_pre_read(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        nonlocal drifted
        result = original_call(method, params)
        if method == "thread/goal/get" and not drifted:
            target.write_bytes(b"{}\n")
            drifted = True
        return result

    rpc.call = mutate_after_pre_read  # type: ignore[method-assign]
    with pytest.raises(
        RUNTIME.VISIBLE.IncarnationHomeError,
        match="changed during validation",
    ):
        ADAPTER.run_goal_transition(args)

    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 0
    assert not receipt_path.exists()


def test_generic_adapter_executes_against_the_current_public_goal_set_surface(
    tmp_path: Path,
) -> None:
    owner_path = tmp_path / "owner.json"
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:non-atomic",
    )
    decision = _decision(request)

    endpoint = tmp_path / "non-atomic.sock"
    owner = _owner(endpoint)
    owner_path.write_text(json.dumps(owner), encoding="utf-8")
    rpc = FakeGoalRpc(endpoint, status="active")
    receipt = ADAPTER.execute_goal_transition(
        request,
        decision,
        owner,
        owner_path,
        rpc.endpoint,
        rpc_factory=lambda _endpoint: rpc,
        attempt_path=tmp_path / "non-atomic.attempt.json",
    )
    assert receipt["status"] == "executed"
    assert receipt["lifecycle"]["transition_proof"]["kind"] == (
        "request_response_post_read"
    )
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1
    assert [method for method, _params in rpc.calls].count("thread/goal/get") == 2


def test_programmatic_adapter_serializes_one_semantic_attempt_across_paths(
    tmp_path: Path,
) -> None:
    endpoint = tmp_path / "concurrent-programmatic.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner-concurrent-programmatic.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:concurrent-programmatic",
    )
    decision = _decision(request)
    rpc = FakeGoalRpc(endpoint, status="active")
    first_adapter = ADAPTER.CodexGoalLifecycleAdapter(
        owner=owner,
        owner_path=owner_path,
        endpoint=endpoint,
        rpc_factory=lambda _endpoint: rpc,
        attempt_path=tmp_path / "concurrent-programmatic-first.attempt.json",
    )
    second_adapter = ADAPTER.CodexGoalLifecycleAdapter(
        owner=owner,
        owner_path=owner_path,
        endpoint=endpoint,
        rpc_factory=lambda _endpoint: rpc,
        attempt_path=tmp_path / "concurrent-programmatic-second.attempt.json",
    )
    callers_ready = threading.Barrier(2)
    mutation_entered = threading.Event()
    release_mutation = threading.Event()
    original_call = rpc.call

    def blocking_call(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        if method == "thread/goal/set":
            mutation_entered.set()
            assert release_mutation.wait(timeout=5)
        return original_call(method, params)

    rpc.call = blocking_call  # type: ignore[method-assign]

    def invoke(adapter: Any) -> dict[str, Any]:
        callers_ready.wait(timeout=5)
        return adapter.execute_goal_transition(request, decision)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(invoke, first_adapter),
            executor.submit(invoke, second_adapter),
        ]
        assert mutation_entered.wait(timeout=5)
        assert all(not future.done() for future in futures)
        release_mutation.set()
        receipts = [future.result(timeout=5) for future in futures]

    assert {receipt["status"] for receipt in receipts} == {"executed"}
    assert sum(
        receipt["lifecycle"].get("recovery") is not None for receipt in receipts
    ) == 1
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1
    attempt_paths = [
        tmp_path / "concurrent-programmatic-first.attempt.json",
        tmp_path / "concurrent-programmatic-second.attempt.json",
    ]
    assert sum(path.exists() for path in attempt_paths) == 1


def test_crossed_receipt_and_attempt_coordinates_share_physical_lock(
    tmp_path: Path,
) -> None:
    owner_a = _owner()
    owner_a["goal_id"] = "goal:crossed-a"
    owner_a["goal_ref"] = _ref("goal:crossed-a").model_dump(mode="json")
    owner_b = _owner()
    owner_b["goal_id"] = "goal:crossed-b"
    owner_b["thread_id"] = "thread:crossed-b"
    owner_b["goal_ref"] = _ref("goal:crossed-b").model_dump(mode="json")
    request_a = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:crossed-coordinate-a",
    ).model_copy(update={"goal_ref": _ref("goal:crossed-a")})
    request_b = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:crossed-coordinate-b",
    ).model_copy(update={"goal_ref": _ref("goal:crossed-b")})
    shared_coordinate = tmp_path / "crossed-a.attempt.json"
    receipt_a = tmp_path / "crossed-a.receipt.json"
    attempt_b = tmp_path / "crossed-b.attempt.json"
    contender_started = threading.Event()
    contender_entered = threading.Event()

    def contend() -> None:
        contender_started.set()
        with ADAPTER._goal_transition_attempt_locks(
            request_b,
            owner_b,
            attempt_b,
            additional_physical_paths=(shared_coordinate,),
        ):
            contender_entered.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with ADAPTER._goal_transition_attempt_locks(
            request_a,
            owner_a,
            shared_coordinate,
            additional_physical_paths=(receipt_a,),
        ):
            future = pool.submit(contend)
            assert contender_started.wait(timeout=2)
            assert not contender_entered.wait(timeout=0.2)
            assert not future.done()

        assert contender_entered.wait(timeout=2)
        future.result(timeout=2)


def test_programmatic_adapter_serializes_different_requests_by_goal_identity(
    tmp_path: Path,
) -> None:
    endpoint = tmp_path / "concurrent-goal-identity.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner-concurrent-goal-identity.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    requests = [
        _request(
            observed="active",
            desired="paused",
            kind="delegation_yield",
            request_id=f"request:goal-identity-{index}",
        )
        for index in range(2)
    ]
    decisions = [_decision(request) for request in requests]
    rpc = FakeGoalRpc(endpoint, status="active")
    adapters = [
        ADAPTER.CodexGoalLifecycleAdapter(
            owner=owner,
            owner_path=owner_path,
            endpoint=endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=tmp_path / f"goal-identity-{index}.attempt.json",
        )
        for index in range(2)
    ]
    callers_ready = threading.Barrier(2)
    preconditions_ready = threading.Barrier(2)
    original_call = rpc.call

    def synchronized_precondition(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        if method == "thread/goal/get" and rpc.status == "active":
            try:
                preconditions_ready.wait(timeout=0.25)
            except threading.BrokenBarrierError:
                pass
        return original_call(method, params)

    rpc.call = synchronized_precondition  # type: ignore[method-assign]

    def invoke(index: int) -> dict[str, Any]:
        callers_ready.wait(timeout=5)
        return adapters[index].execute_goal_transition(
            requests[index], decisions[index]
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = [
            future.result(timeout=5)
            for future in [executor.submit(invoke, index) for index in range(2)]
        ]

    assert {receipt["status"] for receipt in receipts} == {"executed", "replayed"}
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


def test_programmatic_adapter_claims_shared_attempt_path_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = tmp_path / "shared-physical-attempt.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner-shared-physical-attempt.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    requests = [
        _request(
            observed="active",
            desired="paused",
            kind="delegation_yield",
            request_id=f"request:shared-physical-attempt-{index}",
        )
        for index in range(2)
    ]
    decisions = [_decision(request) for request in requests]
    shared_attempt = tmp_path / "shared-physical.attempt.json"
    rpc = FakeGoalRpc(endpoint, status="active")
    adapters = [
        ADAPTER.CodexGoalLifecycleAdapter(
            owner=owner,
            owner_path=owner_path,
            endpoint=endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=shared_attempt,
        )
        for _index in range(2)
    ]
    # Isolate the physical-coordinate guard from the wider Goal lock so this
    # regression proves the caller-selected path has its own atomic claim.
    monkeypatch.setattr(
        RUNTIME,
        "_pause_attempt_lock",
        lambda _owner: contextlib.nullcontext(),
    )
    callers_ready = threading.Barrier(2)
    preconditions_ready = threading.Barrier(2)
    original_call = rpc.call

    def synchronized_precondition(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        if method == "thread/goal/get" and rpc.status == "active":
            try:
                preconditions_ready.wait(timeout=0.25)
            except threading.BrokenBarrierError:
                pass
        return original_call(method, params)

    rpc.call = synchronized_precondition  # type: ignore[method-assign]

    def invoke(index: int) -> dict[str, Any]:
        callers_ready.wait(timeout=5)
        return adapters[index].execute_goal_transition(
            requests[index], decisions[index]
        )

    receipts: list[dict[str, Any]] = []
    failures: list[Exception] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(invoke, index) for index in range(2)]
        for future in futures:
            try:
                receipts.append(future.result(timeout=5))
            except RUNTIME.ExternalCodexReturnError as exc:
                failures.append(exc)

    assert len(receipts) == 1
    assert receipts[0]["status"] == "executed"
    assert len(failures) == 1
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


def test_cli_adapter_serializes_one_semantic_attempt_across_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _request_path, _decision_path, first_receipt, rpc = _cli_fixture(
        tmp_path,
        monkeypatch,
        request_id="request:concurrent-cli-receipts",
    )
    second_receipt = tmp_path / "second-receipt.json"
    second_args = SimpleNamespace(
        request=args.request,
        decision=args.decision,
        owner=args.owner,
        receipt=str(second_receipt),
    )
    callers_ready = threading.Barrier(2)
    mutation_entered = threading.Event()
    release_mutation = threading.Event()
    original_call = rpc.call

    def blocking_call(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        if method == "thread/goal/set":
            mutation_entered.set()
            assert release_mutation.wait(timeout=5)
        return original_call(method, params)

    rpc.call = blocking_call  # type: ignore[method-assign]

    def invoke(invocation: SimpleNamespace) -> dict[str, Any]:
        callers_ready.wait(timeout=5)
        return ADAPTER.run_goal_transition(invocation)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(invoke, args),
            executor.submit(invoke, second_args),
        ]
        assert mutation_entered.wait(timeout=5)
        assert all(not future.done() for future in futures)
        release_mutation.set()
        receipts = [future.result(timeout=5) for future in futures]

    assert {receipt["status"] for receipt in receipts} == {"executed"}
    assert sum(
        receipt["lifecycle"].get("recovery") is not None for receipt in receipts
    ) == 1
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1
    attempt_paths = [
        ADAPTER._attempt_path(first_receipt),
        ADAPTER._attempt_path(second_receipt),
    ]
    assert sum(path.exists() for path in attempt_paths) == 1


def test_cli_retry_after_reverse_uses_original_semantic_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _request_path, _decision_path, first_receipt, rpc = _cli_fixture(
        tmp_path,
        monkeypatch,
        request_id="request:durable-semantic-attempt",
    )
    first = ADAPTER.run_goal_transition(args)
    first_attempt = Path(first["attempt_artifact"]["ref"])
    assert first_attempt == ADAPTER._attempt_path(first_receipt).resolve()
    assert first_attempt.exists()

    # A separately accepted reverse transition may legitimately restore the
    # original state.  Replaying this old idempotency key through another
    # receipt must still resolve the original completed attempt and refuse a
    # second native mutation.
    rpc.status = "active"
    second_receipt = tmp_path / "durable-semantic-attempt-retry.json"
    second_args = SimpleNamespace(
        request=args.request,
        decision=args.decision,
        owner=args.owner,
        receipt=str(second_receipt),
    )
    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="already has a durable attempt",
    ):
        ADAPTER.run_goal_transition(second_args)

    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1
    assert not ADAPTER._attempt_path(second_receipt).exists()
    assert not second_receipt.exists()


def test_cli_read_only_completion_blocks_later_mutation_after_reverse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, request_path, decision_path, first_receipt, rpc = _cli_fixture(
        tmp_path,
        monkeypatch,
        request_id="request:read-only-completion",
    )
    request = _request(
        observed="active",
        desired="active",
        kind="accepted_return",
        request_id="request:read-only-completion",
    )
    decision = _decision(request)
    request_path.write_bytes(
        RUNTIME._canonical_bytes(request.model_dump(mode="json")) + b"\n"
    )
    decision_path.write_bytes(
        RUNTIME._canonical_bytes(decision.model_dump(mode="json")) + b"\n"
    )

    first = ADAPTER.run_goal_transition(args)
    first_attempt = Path(first["attempt_artifact"]["ref"])
    assert json.loads(first_attempt.read_text(encoding="utf-8"))["state"] == (
        "read_only_recorded"
    )
    assert not any(method == "thread/goal/set" for method, _params in rpc.calls)

    rpc.status = "paused"
    second_receipt = tmp_path / "read-only-completion-retry.json"
    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="already has a durable attempt",
    ):
        ADAPTER.run_goal_transition(
            SimpleNamespace(
                request=args.request,
                decision=args.decision,
                owner=args.owner,
                receipt=str(second_receipt),
            )
        )

    assert first_attempt.exists()
    assert not any(method == "thread/goal/set" for method, _params in rpc.calls)
    assert not ADAPTER._attempt_path(second_receipt).exists()
    assert not second_receipt.exists()


def test_cli_missing_anchored_read_only_attempt_is_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, request_path, decision_path, _first_receipt, rpc = _cli_fixture(
        tmp_path,
        monkeypatch,
        request_id="request:missing-read-only-attempt",
    )
    request = _request(
        observed="active",
        desired="active",
        kind="accepted_return",
        request_id="request:missing-read-only-attempt",
    )
    decision = _decision(request)
    request_path.write_bytes(
        RUNTIME._canonical_bytes(request.model_dump(mode="json")) + b"\n"
    )
    decision_path.write_bytes(
        RUNTIME._canonical_bytes(decision.model_dump(mode="json")) + b"\n"
    )
    first = ADAPTER.run_goal_transition(args)
    first_attempt = Path(first["attempt_artifact"]["ref"])
    first_attempt.unlink()

    rpc.status = "paused"
    retry_receipt = tmp_path / "missing-read-only-attempt-retry.json"
    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="anchored attempt reservation is missing",
    ):
        ADAPTER.run_goal_transition(
            SimpleNamespace(
                request=args.request,
                decision=args.decision,
                owner=args.owner,
                receipt=str(retry_receipt),
            )
        )

    assert not any(method == "thread/goal/set" for method, _params in rpc.calls)
    assert not retry_receipt.exists()


@pytest.mark.parametrize("failure_stage", ("discovery", "rpc_setup"))
def test_cli_unstarted_anchor_allows_retry_after_transient_transport_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    args, _request_path, _decision_path, receipt_path, rpc = _cli_fixture(
        tmp_path,
        monkeypatch,
        request_id=f"request:unstarted-anchor-{failure_stage}",
    )
    failed_once = False

    if failure_stage == "discovery":
        def flaky_discovery(
            _owner: dict[str, Any], **_kwargs: object
        ) -> tuple[Path, str]:
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise RUNTIME.ExternalCodexReturnError(
                    "simulated transient endpoint discovery failure"
                )
            return rpc.endpoint, "test-fixture"

        monkeypatch.setattr(RUNTIME, "discover_app_server_socket", flaky_discovery)
    else:
        def flaky_rpc_factory(_endpoint: Path) -> FakeGoalRpc:
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise RUNTIME.ExternalCodexReturnError(
                    "simulated transient RPC setup failure"
                )
            return rpc

        monkeypatch.setattr(RUNTIME, "UnixWebSocketRpc", flaky_rpc_factory)

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="simulated transient",
    ):
        ADAPTER.run_goal_transition(args)

    anchors = list((tmp_path / "semantic-attempt-state").glob("*.json"))
    assert len(anchors) == 1
    assert json.loads(anchors[0].read_text(encoding="utf-8"))["attempt_started"] is False
    assert not ADAPTER._attempt_path(receipt_path).exists()
    assert not receipt_path.exists()

    result = ADAPTER.run_goal_transition(args)

    assert result["status"] == "executed"
    assert json.loads(anchors[0].read_text(encoding="utf-8"))["attempt_started"] is True
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


def test_cli_unstarted_anchor_rebinds_after_original_parent_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _request_path, _decision_path, _receipt_path, rpc = _cli_fixture(
        tmp_path,
        monkeypatch,
        request_id="request:unstarted-anchor-parent-cleanup",
    )
    original_job = tmp_path / "original-job"
    original_job.mkdir(mode=0o700)
    original_receipt = original_job / "receipt.json"
    args.receipt = str(original_receipt)
    failed_once = False

    def flaky_discovery(
        _owner: dict[str, Any], **_kwargs: object
    ) -> tuple[Path, str]:
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise RUNTIME.ExternalCodexReturnError(
                "simulated transient endpoint discovery failure"
            )
        return rpc.endpoint, "test-fixture"

    monkeypatch.setattr(RUNTIME, "discover_app_server_socket", flaky_discovery)

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="simulated transient",
    ):
        ADAPTER.run_goal_transition(args)

    anchors = list((tmp_path / "semantic-attempt-state").glob("*.json"))
    assert len(anchors) == 1
    initial_anchor = json.loads(anchors[0].read_text(encoding="utf-8"))
    assert initial_anchor["attempt_started"] is False
    assert initial_anchor["attempt_ref"] == str(
        ADAPTER._attempt_path(original_receipt).resolve()
    )
    original_job.rmdir()

    replacement_job = tmp_path / "replacement-job"
    replacement_job.mkdir(mode=0o700)
    replacement_receipt = replacement_job / "receipt.json"
    args.receipt = str(replacement_receipt)

    result = ADAPTER.run_goal_transition(args)

    rebound_anchor = json.loads(anchors[0].read_text(encoding="utf-8"))
    replacement_attempt = ADAPTER._attempt_path(replacement_receipt)
    assert result["status"] == "executed"
    assert rebound_anchor["attempt_started"] is True
    assert rebound_anchor["attempt_ref"] == str(replacement_attempt.resolve())
    assert replacement_attempt.exists()
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


def test_cli_retry_after_runtime_reset_uses_persistent_semantic_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _request_path, _decision_path, first_receipt, rpc = _cli_fixture(
        tmp_path,
        monkeypatch,
        request_id="request:persistent-semantic-attempt",
    )
    first = ADAPTER.run_goal_transition(args)
    first_attempt = Path(first["attempt_artifact"]["ref"])

    # Runtime locks are advisory and may disappear across a reboot. Persistent
    # owner state must still bind the idempotency key to the first attempt.
    replacement_lock_root = tmp_path / "replacement-runtime-locks"
    replacement_lock_root.mkdir(mode=0o700)
    monkeypatch.setattr(
        ADAPTER,
        "_semantic_attempt_lock_root",
        lambda: replacement_lock_root,
    )
    rpc.status = "active"
    second_receipt = tmp_path / "persistent-semantic-attempt-retry.json"
    second_args = SimpleNamespace(
        request=args.request,
        decision=args.decision,
        owner=args.owner,
        receipt=str(second_receipt),
    )
    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="already has a durable attempt",
    ):
        ADAPTER.run_goal_transition(second_args)

    assert first_attempt.exists()
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1
    assert not ADAPTER._attempt_path(second_receipt).exists()
    assert not second_receipt.exists()


def test_programmatic_semantic_lock_survives_endpoint_rebinding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_endpoint = tmp_path / "old" / "app-server.sock"
    new_endpoint = tmp_path / "new" / "app-server.sock"
    old_endpoint.parent.mkdir()
    new_endpoint.parent.mkdir()
    owner = _owner()
    owner["transport_posture"] = "resolve-current-local-codex-app-server"
    owner_path = tmp_path / "owner-endpoint-rebinding.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:endpoint-rebinding",
    )
    decision = _decision(request)
    rpc = FakeGoalRpc(old_endpoint, status="active")
    discovery_calls: list[Path] = []

    def discover(
        _owner: dict[str, Any], **_kwargs: object
    ) -> tuple[Path, str]:
        endpoint = old_endpoint if not discovery_calls else new_endpoint
        discovery_calls.append(endpoint)
        return endpoint, "test-rebinding"

    monkeypatch.setattr(RUNTIME, "discover_app_server_socket", discover)
    adapters = [
        ADAPTER.CodexGoalLifecycleAdapter(
            owner=owner,
            owner_path=owner_path,
            endpoint=old_endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=tmp_path / f"endpoint-rebinding-{index}.attempt.json",
        )
        for index in range(2)
    ]
    callers_ready = threading.Barrier(2)
    mutation_entered = threading.Event()
    release_mutation = threading.Event()
    original_call = rpc.call

    def blocking_call(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        if method == "thread/goal/set":
            mutation_entered.set()
            assert release_mutation.wait(timeout=5)
        return original_call(method, params)

    rpc.call = blocking_call  # type: ignore[method-assign]

    def invoke(adapter: Any) -> dict[str, Any]:
        callers_ready.wait(timeout=5)
        return adapter.execute_goal_transition(request, decision)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(invoke, adapter) for adapter in adapters]
        assert mutation_entered.wait(timeout=5)
        assert discovery_calls == [old_endpoint]
        assert all(not future.done() for future in futures)
        release_mutation.set()
        receipts = [future.result(timeout=5) for future in futures]

    assert discovery_calls == [old_endpoint, new_endpoint]
    assert {receipt["status"] for receipt in receipts} == {"executed"}
    assert sum(
        receipt["lifecycle"].get("recovery") is not None for receipt in receipts
    ) == 1
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


def test_programmatic_adapter_rejects_owner_drift_before_mutation(
    tmp_path: Path,
) -> None:
    endpoint = tmp_path / "owner-drift-before-mutation.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner-drift-before-mutation.json"
    owner_bytes = RUNTIME._canonical_bytes(owner) + b"\n"
    owner_path.write_bytes(owner_bytes)
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:owner-drift-before-mutation",
    )
    decision = _decision(request)
    attempt_path = tmp_path / "owner-drift-before-mutation.attempt.json"
    rpc = FakeGoalRpc(endpoint, status="active")
    original_call = rpc.call
    goal_get_count = 0

    def drift_after_precondition(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        nonlocal goal_get_count
        result = original_call(method, params)
        if method == "thread/goal/get":
            goal_get_count += 1
            if goal_get_count == 1:
                owner_path.write_bytes(b"{}\n")
        return result

    rpc.call = drift_after_precondition  # type: ignore[method-assign]

    with pytest.raises(
        RUNTIME.VISIBLE.IncarnationHomeError,
        match="changed during validation",
    ):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=attempt_path,
        )

    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 0
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt["owner_sha256"] == RUNTIME._sha256_bytes(owner_bytes)


def test_programmatic_adapter_rejects_owner_drift_after_proof_persistence(
    tmp_path: Path,
) -> None:
    endpoint = tmp_path / "owner-drift-after-proof.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner-drift-after-proof.json"
    owner_bytes = RUNTIME._canonical_bytes(owner) + b"\n"
    owner_path.write_bytes(owner_bytes)
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:owner-drift-after-proof",
    )
    decision = _decision(request)
    attempt_path = tmp_path / "owner-drift-after-proof.attempt.json"
    rpc = FakeGoalRpc(endpoint, status="active")
    original_call = rpc.call
    goal_get_count = 0

    def drift_after_post_read(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        nonlocal goal_get_count
        result = original_call(method, params)
        if method == "thread/goal/get":
            goal_get_count += 1
            if goal_get_count == 2:
                owner_path.write_bytes(b"{}\n")
        return result

    rpc.call = drift_after_post_read  # type: ignore[method-assign]

    with pytest.raises(
        RUNTIME.VISIBLE.IncarnationHomeError,
        match="changed during validation",
    ):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=attempt_path,
        )

    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt["state"] == "proof_recorded"
    assert attempt["owner_sha256"] == RUNTIME._sha256_bytes(owner_bytes)


def test_generic_adapter_reconciles_a_lost_set_response_without_a_second_set(
    tmp_path: Path,
) -> None:
    endpoint = tmp_path / "response-loss.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner-response-loss.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:response-loss",
    )
    decision = _decision(request)
    attempt_path = tmp_path / "response-loss.attempt.json"
    rpc = FakeGoalRpc(endpoint, status="active")
    rpc.lose_goal_set_response = True

    with pytest.raises(RUNTIME.ExternalCodexReturnError, match="response loss"):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=attempt_path,
        )
    dispatched = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert dispatched["state"] == "dispatched"
    assert "goal_response" not in dispatched

    rpc.lose_goal_set_response = False
    receipt = ADAPTER.execute_goal_transition(
        request,
        decision,
        owner,
        owner_path,
        endpoint,
        rpc_factory=lambda _endpoint: rpc,
        attempt_path=attempt_path,
    )
    assert receipt["status"] == "executed"
    assert receipt["lifecycle"]["recovery"]["mutation_response_available"] is False
    assert receipt["lifecycle"]["transition_proof"]["kind"] == (
        "dispatch_reconciled_post_read"
    )
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1

    historical_post_read = json.loads(attempt_path.read_text(encoding="utf-8"))[
        "post_read_response"
    ]
    rpc.goal_get_extra = {"server_metadata": {"revision": 2}}
    replay = ADAPTER.execute_goal_transition(
        request,
        decision,
        owner,
        owner_path,
        endpoint,
        rpc_factory=lambda _endpoint: rpc,
        attempt_path=attempt_path,
    )
    assert replay["lifecycle"]["result_response"] == historical_post_read
    assert replay["lifecycle"]["result_response"] != {
        "goal": {"threadId": "thread:test", "status": "paused"},
        "server_metadata": {"revision": 2},
    }
    assert replay["lifecycle"]["recovery"]["mutation_response_available"] is False
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


def test_generic_adapter_legacy_recovery_projects_its_stored_mutation_response(
    tmp_path: Path,
) -> None:
    endpoint = tmp_path / "legacy-recovery.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner-legacy-recovery.json"
    owner_path.write_bytes(RUNTIME._canonical_bytes(owner) + b"\n")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:legacy-recovery",
    )
    decision = _decision(request)
    attempt_path = tmp_path / "legacy-recovery.attempt.json"
    rpc = FakeGoalRpc(endpoint, status="active")
    ADAPTER.execute_goal_transition(
        request,
        decision,
        owner,
        owner_path,
        endpoint,
        rpc_factory=lambda _endpoint: rpc,
        attempt_path=attempt_path,
    )

    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    proof = attempt["transition_proof"]
    attempt["transition_proof"] = {
        key: proof[key]
        for key in (
            "schema_version",
            "kind",
            "method",
            "thread_id",
            "from_status",
            "to_status",
            "precondition_sha256",
            "request_id",
            "request_sha256",
            "goal_response_sha256",
        )
    }
    attempt["transition_proof"]["schema_version"] = (
        ADAPTER.LEGACY_GOAL_TRANSITION_PROOF_SCHEMA_VERSION
    )
    attempt["transition_proof"]["kind"] = "server_compare_and_set"
    historical_mutation_response = attempt["goal_response"]
    attempt["post_read_response"] = {
        "goal": {"threadId": "thread:test", "status": "paused"},
        "server_metadata": {"legacy_optional": True},
    }
    attempt_path.write_bytes(RUNTIME._canonical_bytes(attempt) + b"\n")
    rpc.goal_get_extra = {"server_metadata": {"revision": 2}}

    recovered = ADAPTER.execute_goal_transition(
        request,
        decision,
        owner,
        owner_path,
        endpoint,
        rpc_factory=lambda _endpoint: rpc,
        attempt_path=attempt_path,
    )

    assert recovered["lifecycle"]["result_response"] == historical_mutation_response
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


@pytest.mark.parametrize("missing_marker", ("mutation_reserved", "mutation_dispatched"))
def test_generic_adapter_requires_both_dispatch_markers_for_recovery(
    tmp_path: Path, missing_marker: str
) -> None:
    _receipt, rpc = _run_transition(
        tmp_path, initial="active", desired="paused", kind="delegation_yield"
    )
    endpoint = tmp_path / "delegation_yield.sock"
    owner = _owner(endpoint)
    owner_path = tmp_path / "owner-delegation_yield.json"
    attempt_path = tmp_path / "delegation_yield.attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt.pop(missing_marker)
    attempt_path.write_bytes(RUNTIME._canonical_bytes(attempt) + b"\n")
    before_calls = list(rpc.calls)
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:delegation_yield",
    )
    decision = _decision(request)

    with pytest.raises(
        RUNTIME.ExternalCodexReturnError,
        match="(schema mismatch|dispatch marker)",
    ):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            endpoint,
            rpc_factory=lambda _endpoint: rpc,
            attempt_path=attempt_path,
        )

    assert rpc.calls == before_calls
