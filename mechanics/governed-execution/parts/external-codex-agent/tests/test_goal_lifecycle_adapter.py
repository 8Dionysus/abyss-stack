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
    supports_atomic_goal_transition = True

    def __init__(self, endpoint: Path, *, status: str) -> None:
        self.endpoint = endpoint
        self.status = status
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self.counter = 0
        self.mutation_response_extra: dict[str, object] = {}

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
        response.update(self.mutation_response_extra)
        prepare_callback = getattr(self, "request_prepare_callback", None)
        if callable(prepare_callback):
            prepare_callback("thread/goal/set", params, request_id, payload)
        self.calls.append(("thread/goal/set", params))
        issued_callback = getattr(self, "request_issued_callback", None)
        if callable(issued_callback):
            issued_callback("thread/goal/set", params, request_id, payload)
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
    args, _request_path, _decision_path, receipt_path, rpc = _cli_fixture(
        tmp_path, monkeypatch, request_id="request:cli"
    )
    rpc.mutation_response_extra = {"set_response_only": True}

    first = ADAPTER.run_goal_transition(args)
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
    original_transition = rpc.atomic_goal_transition

    def mutate_request_after_mutation(**kwargs: object) -> dict[str, object]:
        result = original_transition(**kwargs)
        request_path.write_bytes(b"{}\n")
        return result

    rpc.atomic_goal_transition = mutate_request_after_mutation  # type: ignore[method-assign]
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


def test_generic_adapter_refuses_the_current_public_non_atomic_surface(tmp_path: Path) -> None:
    owner_path = tmp_path / "owner.json"
    request = _request(
        observed="active",
        desired="paused",
        kind="delegation_yield",
        request_id="request:non-atomic",
    )
    decision = _decision(request)

    class NonAtomic(FakeGoalRpc):
        supports_atomic_goal_transition = False

    endpoint = tmp_path / "non-atomic.sock"
    owner = _owner(endpoint)
    owner_path.write_text(json.dumps(owner), encoding="utf-8")
    rpc = NonAtomic(endpoint, status="active")
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
