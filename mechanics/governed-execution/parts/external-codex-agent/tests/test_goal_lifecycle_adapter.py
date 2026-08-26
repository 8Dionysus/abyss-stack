from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
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


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


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


def _owner() -> dict[str, str]:
    return {
        "schema_version": RUNTIME.GOAL_LIFECYCLE_OWNER_SCHEMA_VERSION,
        "owner_id": "holder:master:test",
        "owner_repo": "codex-goal",
        "goal_id": "goal:test",
        "thread_id": "thread:test",
        "runtime": "codex",
        "transport_posture": "explicit-endpoint",
        "acceptance_posture": "owner-return-pending",
    }


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
        observed_by=_provenance("aoa-agents", "context/goal-dag-ownership"),
    )
    return resolve_goal_lifecycle(request, context)


class FakeGoalRpc:
    supports_atomic_goal_transition = True

    def __init__(self, endpoint: Path, *, status: str) -> None:
        self.endpoint = endpoint
        self.status = status
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self.counter = 0

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
            return {"goal": {"threadId": "thread:test", "status": self.status}}
        raise AssertionError(f"unexpected non-lifecycle method: {method}")

    def atomic_goal_transition(
        self,
        *,
        owner: dict[str, object],
        precondition: dict[str, object],
        status: str,
    ) -> dict[str, object]:
        request_id = self.counter + 1
        params = {"threadId": owner["thread_id"], "status": status}
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "thread/goal/set",
            "params": params,
        }
        response = {"goal": {"threadId": "thread:test", "status": status}}
        self.calls.append(("thread/goal/set", params))
        self.status = status
        return {
            "goal_response": response,
            "request_frame": payload,
            "transition_proof": {
                "schema_version": ADAPTER.GOAL_TRANSITION_PROOF_SCHEMA_VERSION,
                "kind": "server_compare_and_set",
                "method": "thread/goal/set",
                "thread_id": "thread:test",
                "from_status": precondition["observed_state"],
                "to_status": status,
                "precondition_sha256": precondition["goal_response_sha256"],
                "request_id": request_id,
                "request_sha256": _digest(payload),
                "goal_response_sha256": _digest(response),
            },
        }


def _run_transition(tmp_path: Path, *, initial: str, desired: str, kind: str) -> tuple[dict[str, Any], FakeGoalRpc]:
    owner = _owner()
    owner_path = tmp_path / f"owner-{kind}.json"
    owner_path.write_text(json.dumps(owner), encoding="utf-8")
    endpoint = tmp_path / f"{kind}.sock"
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
    )
    return receipt, rpc


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
    assert [method for method, _params in rpc.calls].count("thread/goal/get") == 1
    assert not any(method == "thread/goal/set" for method, _params in rpc.calls)


def test_generic_adapter_cli_route_replays_canonical_receipt(
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
        request_id="request:cli",
    )
    decision = _decision(request)
    request_path.write_bytes(
        RUNTIME._canonical_bytes(request.model_dump(mode="json")) + b"\n"
    )
    decision_path.write_bytes(
        RUNTIME._canonical_bytes(decision.model_dump(mode="json")) + b"\n"
    )
    rpc = FakeGoalRpc(tmp_path / "cli.sock", status="active")
    monkeypatch.setattr(
        RUNTIME,
        "discover_app_server_socket",
        lambda _owner: (rpc.endpoint, "test-fixture"),
    )
    monkeypatch.setattr(RUNTIME, "UnixWebSocketRpc", lambda _endpoint: rpc)
    args = SimpleNamespace(
        request=str(request_path),
        decision=str(decision_path),
        owner=str(owner_path),
        receipt=str(receipt_path),
    )

    first = ADAPTER.run_goal_transition(args)
    second = ADAPTER.run_goal_transition(args)

    assert first == second
    assert first["receipt_ref"] == str(receipt_path.resolve())
    assert first["transport"]["resolution"] == "test-fixture"
    assert [method for method, _params in rpc.calls].count("thread/goal/set") == 1


def test_generic_adapter_refuses_the_current_public_non_atomic_surface(tmp_path: Path) -> None:
    owner = _owner()
    owner_path = tmp_path / "owner.json"
    owner_path.write_text(json.dumps(owner), encoding="utf-8")
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:non-atomic",
    )
    decision = _decision(request)

    class NonAtomic(FakeGoalRpc):
        supports_atomic_goal_transition = False

    rpc = NonAtomic(tmp_path / "non-atomic.sock", status="active")
    with pytest.raises(RUNTIME.ExternalCodexReturnError, match="compare-and-set"):
        ADAPTER.execute_goal_transition(
            request,
            decision,
            owner,
            owner_path,
            rpc.endpoint,
            rpc_factory=lambda _endpoint: rpc,
        )
    assert not any(method == "thread/goal/set" for method, _params in rpc.calls)
