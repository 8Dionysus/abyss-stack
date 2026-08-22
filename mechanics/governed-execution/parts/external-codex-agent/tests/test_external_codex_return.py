from __future__ import annotations

import fcntl
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


PART = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "external_codex_return", PART / "external_codex_return.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def owner(*, goal: str, thread: str, endpoint: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": MODULE.RETURN_OWNER_SCHEMA_VERSION,
        "owner_id": f"holder:codex-goal-master:{goal}",
        "owner_repo": "codex-goal",
        "goal_id": goal,
        "thread_id": thread,
        "runtime": "codex",
        "transport_posture": "explicit-endpoint",
        "acceptance_posture": "delivery_pending_master_filter",
    }
    if endpoint is not None:
        value["transport_endpoint"] = endpoint
    return value


def pause_owner(
    *, goal: str, thread: str, endpoint: str | None = None
) -> dict[str, object]:
    value = owner(goal=goal, thread=thread, endpoint=endpoint)
    value["schema_version"] = MODULE.PAUSE_OWNER_SCHEMA_VERSION
    return value


class FakeRpc:
    def __init__(
        self,
        endpoint: Path,
        *,
        active_turn: str | None,
        goal_status: str = "active",
        goal_id: str = "goal-dynamic-1",
        thread_id: str = "thread-dynamic-1",
        bounded_turns: bool = False,
        fallback_active_turn: str | None = None,
        goal_set_status: str = "active",
    ) -> None:
        self.endpoint = endpoint
        self.active_turn = active_turn
        self.goal_status = goal_status
        self.goal_id = goal_id
        self.thread_id = thread_id
        self.bounded_turns = bounded_turns
        self.fallback_active_turn = fallback_active_turn
        self.goal_set_status = goal_set_status
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def __enter__(self) -> "FakeRpc":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        return None

    def notify(self, method: str, params: dict[str, object] | None = None) -> None:
        self.calls.append((method, params))

    def call(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.calls.append((method, params))
        if method == "initialize":
            return {"protocolVersion": "1"}
        if method == "thread/goal/get":
            return {
                "goal": {
                    "threadId": self.thread_id,
                    "status": self.goal_status,
                }
            }
        if method == "thread/goal/set":
            return {
                "goal": {
                    "threadId": self.thread_id,
                    "status": self.goal_set_status,
                }
            }
        if method == "thread/read":
            if self.bounded_turns and params != {
                "threadId": self.thread_id,
                "includeTurns": False,
            }:
                raise AssertionError(params)
            if self.bounded_turns:
                turns = []
            elif self.active_turn is None:
                turns: list[dict[str, object]] = []
            else:
                turns = [{"id": self.active_turn, "status": "inProgress", "items": []}]
            return {"thread": {"id": self.thread_id, "turns": turns}}
        if method == "thread/turns/list":
            if params != {
                "threadId": self.thread_id,
                "limit": 1,
                "itemsView": "notLoaded",
            }:
                raise AssertionError(params)
            turns = []
            if self.fallback_active_turn is not None:
                turns.append(
                    {
                        "id": self.fallback_active_turn,
                        "status": "inProgress",
                        "items": [],
                    }
                )
            return {"data": turns, "nextCursor": "", "backwardsCursor": ""}
        if method == "turn/start":
            return {"turn": {"id": "new-turn", "status": "inProgress", "items": []}}
        if method == "turn/steer":
            return {"turnId": "new-turn"}
        raise AssertionError(method)


@pytest.mark.parametrize(
    ("active_turn", "expected_method"),
    [(None, "turn/start"), ("turn-existing", "turn/steer")],
)
def test_delivery_addresses_dynamic_owner_and_active_or_paused_turn(
    tmp_path: Path,
    active_turn: str | None,
    expected_method: str,
) -> None:
    owner_path = tmp_path / "owner.json"
    owner_value = owner(
        goal="goal-dynamic-1",
        thread="thread-dynamic-1",
        endpoint="unix:/run/user/1000/example.sock",
    )
    owner_path.write_text(json.dumps(owner_value, sort_keys=True) + "\n", encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text('{"responsibility_state":"returned"}\n', encoding="utf-8")
    endpoint = tmp_path / "app-server.sock"
    fake = FakeRpc(endpoint, active_turn=active_turn)
    fake.goal_id = str(owner_value["goal_id"])
    fake.thread_id = str(owner_value["thread_id"])

    receipt = MODULE.deliver_handoff(
        MODULE.validate_return_owner(owner_value),
        owner_path,
        handoff,
        endpoint,
        rpc_factory=lambda path: fake,
    )

    assert receipt["owner"]["goal_id"] == "goal-dynamic-1"
    assert receipt["owner"]["thread_id"] == "thread-dynamic-1"
    assert receipt["goal_status"] == "active"
    assert receipt["delivery_method"] == expected_method
    assert receipt["delivered"] is True
    assert receipt["actions"] == {"handoff_message_sent": True}
    assert receipt["observed"] == {"handoff_delivery": True, "goal_status": "active"}
    assert receipt["goal_binding"]["activation"] == "already_active"
    assert any(method == expected_method for method, _params in fake.calls)
    thread_reads = [params for method, params in fake.calls if method == "thread/read"]
    assert thread_reads == [
        {"threadId": "thread-dynamic-1", "includeTurns": False}
    ]


def test_delivery_uses_bounded_thread_read_for_large_idle_history(
    tmp_path: Path,
) -> None:
    owner_path = tmp_path / "owner.json"
    owner_value = owner(
        goal="goal-bounded",
        thread="thread-bounded",
        endpoint="unix:/run/user/1000/example.sock",
    )
    owner_path.write_text(json.dumps(owner_value, sort_keys=True) + "\n", encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text('{"responsibility_state":"returned"}\n', encoding="utf-8")
    endpoint = tmp_path / "app-server.sock"
    fake = FakeRpc(
        endpoint,
        active_turn=None,
        thread_id="thread-bounded",
        bounded_turns=True,
    )

    receipt = MODULE.deliver_handoff(
        MODULE.validate_return_owner(owner_value),
        owner_path,
        handoff,
        endpoint,
        rpc_factory=lambda path: fake,
    )

    assert receipt["delivery_method"] == "turn/start"
    assert any(method == "turn/start" for method, _params in fake.calls)
    assert any(method == "thread/turns/list" for method, _params in fake.calls)


def test_pause_goal_proves_exact_active_to_paused_transition(
    tmp_path: Path,
) -> None:
    owner_path = tmp_path / "pause-owner.json"
    owner_value = pause_owner(
        goal="goal-pause",
        thread="thread-pause",
        endpoint="unix:/run/user/1000/example.sock",
    )
    owner_path.write_text(
        json.dumps(owner_value, sort_keys=True) + "\n", encoding="utf-8"
    )
    endpoint = tmp_path / "app-server.sock"
    fake = FakeRpc(
        endpoint,
        active_turn=None,
        goal_status="active",
        goal_set_status="paused",
        thread_id="thread-pause",
    )

    receipt = MODULE.pause_goal(
        MODULE.validate_pause_owner(owner_value),
        owner_path,
        endpoint,
        rpc_factory=lambda path: fake,
    )

    assert receipt["schema_version"] == MODULE.PAUSE_RECEIPT_SCHEMA_VERSION
    assert receipt["goal_status"] == "paused"
    assert receipt["goal_binding"]["transition"] == "active_to_paused"
    assert receipt["actions"] == {"goal_lifecycle_set": True}
    assert receipt["observed"] == {
        "goal_lifecycle": "paused",
        "goal_status": "paused",
    }
    assert receipt["owner_acceptance"] == "separate"
    assert receipt["semantic_acceptance"] == "separate"
    assert [method for method, _params in fake.calls] == [
        "initialize",
        "initialized",
        "thread/goal/get",
        "thread/goal/set",
    ]


@pytest.mark.parametrize("goal_status", ["paused", "blocked", "complete"])
def test_pause_goal_refuses_non_active_goal_without_mutation(
    tmp_path: Path,
    goal_status: str,
) -> None:
    owner_path = tmp_path / "pause-owner.json"
    owner_value = pause_owner(
        goal="goal-pause-refuse",
        thread="thread-pause-refuse",
        endpoint="unix:/run/user/1000/example.sock",
    )
    owner_path.write_text(
        json.dumps(owner_value, sort_keys=True) + "\n", encoding="utf-8"
    )
    fake = FakeRpc(
        tmp_path / "app-server.sock",
        active_turn=None,
        goal_status=goal_status,
        thread_id="thread-pause-refuse",
    )

    with pytest.raises(
        MODULE.ExternalCodexReturnError,
        match="not pausable from active state",
    ):
        MODULE.pause_goal(
            MODULE.validate_pause_owner(owner_value),
            owner_path,
            fake.endpoint,
            rpc_factory=lambda path: fake,
        )

    assert not any(method == "thread/goal/set" for method, _params in fake.calls)


def test_run_pause_reserves_and_replays_without_second_transport_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_path = tmp_path / "pause-owner.json"
    owner_value = pause_owner(
        goal="goal-pause-replay",
        thread="thread-pause-replay",
        endpoint="unix:/run/user/1000/example.sock",
    )
    owner_path.write_text(
        json.dumps(owner_value, sort_keys=True) + "\n", encoding="utf-8"
    )
    pause_path = tmp_path / "pause-receipt.json"
    endpoint = tmp_path / "app-server.sock"
    fake = FakeRpc(
        endpoint,
        active_turn=None,
        goal_status="active",
        goal_set_status="paused",
        thread_id="thread-pause-replay",
    )

    monkeypatch.setattr(
        MODULE,
        "discover_app_server_socket",
        lambda _owner: (endpoint, "explicit-endpoint"),
    )
    pause_impl = MODULE.pause_goal

    def pause_once(
        owner_value: dict[str, object],
        owner_file: Path,
        target: Path,
        *,
        owner_bytes: bytes,
        reservation_path: Path | None = None,
        reservation: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return pause_impl(
            owner_value,
            owner_file,
            target,
            owner_bytes=owner_bytes,
            reservation_path=reservation_path,
            reservation=reservation,
            rpc_factory=lambda _path: fake,
        )

    monkeypatch.setattr(MODULE, "pause_goal", pause_once)
    args = SimpleNamespace(
        pause_owner=str(owner_path),
        pause_receipt=str(pause_path),
    )
    first = MODULE.run_pause(args)
    assert first["goal_binding"]["transition"] == "active_to_paused"
    assert first["pause_receipt_ref"] == str(pause_path.resolve())
    assert len([method for method, _params in fake.calls if method == "thread/goal/set"]) == 1

    monkeypatch.setattr(
        MODULE,
        "pause_goal",
        lambda *_args, **_kwargs: pytest.fail("pause transport replayed"),
    )
    second = MODULE.run_pause(args)
    assert second == first


def test_run_pause_reconciles_reserved_mutation_after_receipt_publication_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_path = tmp_path / "pause-owner.json"
    owner_value = pause_owner(
        goal="goal-pause-reconcile",
        thread="thread-pause-reconcile",
        endpoint="unix:/run/user/1000/example.sock",
    )
    owner_path.write_text(
        json.dumps(owner_value, sort_keys=True) + "\n", encoding="utf-8"
    )
    pause_path = tmp_path / "pause-receipt.json"
    endpoint = tmp_path / "app-server.sock"
    fake = FakeRpc(
        endpoint,
        active_turn=None,
        goal_status="active",
        goal_set_status="paused",
        thread_id="thread-pause-reconcile",
    )

    monkeypatch.setattr(
        MODULE,
        "discover_app_server_socket",
        lambda _owner: (endpoint, "explicit-endpoint"),
    )
    pause_impl = MODULE.pause_goal

    def pause_once(
        owner_value: dict[str, object],
        owner_file: Path,
        target: Path,
        *,
        owner_bytes: bytes,
        reservation_path: Path | None = None,
        reservation: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return pause_impl(
            owner_value,
            owner_file,
            target,
            owner_bytes=owner_bytes,
            reservation_path=reservation_path,
            reservation=reservation,
            rpc_factory=lambda _path: fake,
        )

    monkeypatch.setattr(MODULE, "pause_goal", pause_once)
    replace_impl = MODULE._replace_json

    def fail_completed_receipt(path: Path, value: dict[str, object], label: str) -> None:
        if label == "canonical Goal pause receipt" and value.get("paused") is True:
            raise MODULE.ExternalCodexReturnError("injected receipt publication failure")
        replace_impl(path, value, label)

    monkeypatch.setattr(MODULE, "_replace_json", fail_completed_receipt)
    args = SimpleNamespace(
        pause_owner=str(owner_path),
        pause_receipt=str(pause_path),
    )
    with pytest.raises(
        MODULE.ExternalCodexReturnError,
        match="injected receipt publication failure",
    ):
        MODULE.run_pause(args)
    reserved = json.loads(pause_path.read_text(encoding="utf-8"))
    assert reserved["state"] == "reserved"
    assert reserved["precondition"]["goal_status"] == "active"
    assert len([method for method, _params in fake.calls if method == "thread/goal/set"]) == 1

    fake.goal_status = "paused"
    monkeypatch.setattr(MODULE, "_replace_json", replace_impl)
    second = MODULE.run_pause(args)
    assert second["recovery"]["mode"] == "ambiguous_post_mutation"
    assert second["lifecycle"]["response_available"] is False
    assert len([method for method, _params in fake.calls if method == "thread/goal/set"]) == 1


def test_delivery_steers_active_turn_from_bounded_turn_page(
    tmp_path: Path,
) -> None:
    owner_path = tmp_path / "owner.json"
    owner_value = owner(
        goal="goal-page",
        thread="thread-page",
        endpoint="unix:/run/user/1000/example.sock",
    )
    owner_path.write_text(json.dumps(owner_value, sort_keys=True) + "\n", encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text('{"responsibility_state":"returned"}\n', encoding="utf-8")
    endpoint = tmp_path / "app-server.sock"
    fake = FakeRpc(
        endpoint,
        active_turn=None,
        thread_id="thread-page",
        bounded_turns=True,
        fallback_active_turn="turn-from-page",
    )

    receipt = MODULE.deliver_handoff(
        MODULE.validate_return_owner(owner_value),
        owner_path,
        handoff,
        endpoint,
        rpc_factory=lambda path: fake,
    )

    assert receipt["delivery_method"] == "turn/steer"
    assert receipt["active_turn_id"] == "turn-from-page"
    steer_calls = [params for method, params in fake.calls if method == "turn/steer"]
    assert steer_calls[0]["expectedTurnId"] == "turn-from-page"


def test_discovery_skips_stale_socket_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incarnation_home = tmp_path / "incarnation"
    stale = incarnation_home / "app-server-control/app-server-control.sock"
    ambient_home = tmp_path / "ambient"
    current = ambient_home / ".codex/app-server-control/app-server-control.sock"
    monkeypatch.setenv("CODEX_HOME", str(incarnation_home))
    monkeypatch.delenv("AOA_CODEX_HOME", raising=False)
    monkeypatch.delenv("AOA_CODEX_APP_SERVER_SOCKET", raising=False)
    monkeypatch.delenv("CODEX_APP_SERVER_SOCKET", raising=False)
    monkeypatch.setattr(MODULE.Path, "home", classmethod(lambda _cls: ambient_home))

    socket_paths = {stale, current}
    monkeypatch.setattr(
        MODULE.Path,
        "is_socket",
        lambda path: path in socket_paths,
    )
    probed: list[Path] = []

    def probe(path: Path) -> bool:
        probed.append(path)
        return path == current

    monkeypatch.setattr(MODULE, "_socket_is_connectable", probe)

    resolved, posture = MODULE.discover_app_server_socket(
        {"transport_posture": "resolve-current-local-codex-app-server"}
    )

    assert resolved == current
    assert posture == "current_local_codex_app_server"
    assert probed == [stale, current]


def test_existing_return_receipt_is_replayable_without_transport(
    tmp_path: Path,
) -> None:
    owner_path = tmp_path / "owner.json"
    owner_value = owner(
        goal="goal-first",
        thread="thread-first",
        endpoint="unix:/run/user/1000/example.sock",
    )
    owner_path.write_text(json.dumps(owner_value, sort_keys=True) + "\n", encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text('{"responsibility_state":"returned"}\n', encoding="utf-8")
    validated_owner = MODULE.validate_return_owner(owner_value)
    fake = FakeRpc(
        tmp_path / "unused.sock",
        active_turn=None,
        goal_id=str(owner_value["goal_id"]),
        thread_id=str(owner_value["thread_id"]),
    )
    receipt = MODULE.deliver_handoff(
        validated_owner,
        owner_path,
        handoff,
        tmp_path / "unused.sock",
        rpc_factory=lambda path: fake,
    )
    path = tmp_path / "return.json"
    path.write_bytes(MODULE._canonical_bytes(receipt) + b"\n")

    replayed = MODULE._load_existing_return_receipt(
        path,
        owner=validated_owner,
        owner_path=owner_path,
        owner_digest=MODULE._sha256_bytes(owner_path.read_bytes()),
        handoff_path=handoff,
        handoff_digest=MODULE._sha256_bytes(handoff.read_bytes()),
    )

    assert replayed == receipt

    authorized_replay = MODULE._load_authorized_return_receipt(
        {
            "authorization": {
                "authorization_kind": "wake_delivered",
                "evidence_ref": str(path),
            },
            "owner": validated_owner,
            "owner_path": owner_path,
            "owner_digest": MODULE._sha256_bytes(owner_path.read_bytes()),
            "handoff_path": handoff,
            "handoff_digest": MODULE._sha256_bytes(handoff.read_bytes()),
        }
    )
    assert authorized_replay == (path, receipt)

    receipt["handoff_sha256"] = "sha256:" + "0" * 64
    path.write_bytes(MODULE._canonical_bytes(receipt) + b"\n")
    with pytest.raises(MODULE.ExternalCodexReturnError, match="handoff digest"):
        MODULE._load_existing_return_receipt(
            path,
            owner=validated_owner,
            owner_path=owner_path,
            owner_digest=MODULE._sha256_bytes(owner_path.read_bytes()),
            handoff_path=handoff,
            handoff_digest=MODULE._sha256_bytes(handoff.read_bytes()),
        )


@pytest.mark.parametrize("goal_status", ["complete", "blocked", "usageLimited", "budgetLimited"])
def test_delivery_refuses_terminal_or_blocked_goal_without_mutation(
    tmp_path: Path,
    goal_status: str,
) -> None:
    owner_path = tmp_path / "owner.json"
    owner_value = owner(
        goal="goal-terminal",
        thread="thread-terminal",
        endpoint="unix:/run/user/1000/example.sock",
    )
    owner_path.write_text(json.dumps(owner_value, sort_keys=True) + "\n", encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text('{"responsibility_state":"returned"}\n', encoding="utf-8")
    fake = FakeRpc(
        tmp_path / "app-server.sock",
        active_turn=None,
        goal_status=goal_status,
        goal_id=str(owner_value["goal_id"]),
        thread_id=str(owner_value["thread_id"]),
    )

    with pytest.raises(MODULE.ExternalCodexReturnError, match="not wakeable"):
        MODULE.deliver_handoff(
            MODULE.validate_return_owner(owner_value),
            owner_path,
            handoff,
            fake.endpoint,
            rpc_factory=lambda path: fake,
        )

    assert not any(method == "thread/goal/set" for method, _params in fake.calls)
    assert not any(method in {"turn/start", "turn/steer"} for method, _params in fake.calls)


def test_delivery_requires_goal_thread_binding() -> None:
    owner_value = MODULE.validate_return_owner(
        owner(
            goal="goal-bound",
            thread="thread-bound",
            endpoint="unix:/run/user/1000/example.sock",
        )
    )
    goal = {"goalId": "goal-bound", "threadId": "thread-other", "status": "active"}
    with pytest.raises(MODULE.ExternalCodexReturnError, match="different thread"):
        MODULE._validate_goal_binding(goal, owner_value)


def test_handoff_requires_complete_return_owner() -> None:
    owner_value = MODULE.validate_return_owner(
        owner(
            goal="goal-bound",
            thread="thread-bound",
            endpoint="unix:/run/user/1000/example.sock",
        )
    )
    with pytest.raises(MODULE.ExternalCodexReturnError, match="complete"):
        MODULE._validate_handoff_owner(
            {"responsibility_state": "returned"},
            owner_value,
        )
    with pytest.raises(MODULE.ExternalCodexReturnError, match="complete"):
        MODULE._validate_handoff_owner(
            {"return_owner": {"owner_id": owner_value["owner_id"]}},
            owner_value,
        )


def test_handoff_requires_complete_transport_binding() -> None:
    owner_value = MODULE.validate_return_owner(
        owner(
            goal="goal-bound",
            thread="thread-bound",
            endpoint="unix:/run/user/1000/owner.sock",
        )
    )
    supplied = MODULE.validate_return_owner(
        owner(
            goal="goal-bound",
            thread="thread-bound",
            endpoint="unix:/run/user/1000/other.sock",
        )
    )
    with pytest.raises(MODULE.ExternalCodexReturnError, match="does not match"):
        MODULE._validate_handoff_owner(
            {"return_owner": supplied},
            owner_value,
        )


def test_return_owner_rejects_undeclared_binding_fields() -> None:
    owner_value = owner(
        goal="goal-strict",
        thread="thread-strict",
        endpoint="unix:/run/user/1000/owner.sock",
    )
    with pytest.raises(MODULE.ExternalCodexReturnError, match="undeclared fields"):
        MODULE.validate_return_owner({**owner_value, "unexpected": "value"})
    with pytest.raises(MODULE.ExternalCodexReturnError, match="undeclared fields"):
        MODULE.validate_return_owner(
            {**owner_value, "transport": {"endpoint": "sock", "unexpected": "value"}}
        )


def test_existing_authorization_is_validated_before_return_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_value = owner(
        goal="goal-preflight",
        thread="thread-preflight",
        endpoint="unix:/run/user/1000/owner.sock",
    )
    owner_path = tmp_path / "owner.json"
    owner_path.write_bytes(MODULE._canonical_bytes(owner_value) + b"\n")
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text("{}\n", encoding="utf-8")
    holder_path = tmp_path / "holder.json"
    holder_path.write_text("{}\n", encoding="utf-8")
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text('{"foreign":true}\n', encoding="utf-8")
    closure_path = tmp_path / "closure.json"
    return_path = tmp_path / "return.json"
    handoff_value = {"return_owner": owner_value}
    holder_value = {}
    monkeypatch.setattr(
        MODULE,
        "_load_handoff_context",
        lambda *_args, **_kwargs: (
            handoff_value,
            MODULE._canonical_bytes(handoff_value) + b"\n",
            "sha256:" + "1" * 64,
            holder_value,
            b"{}\n",
            "sha256:" + "2" * 64,
        ),
    )
    called = False

    def reject_downstream(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal called
        called = True
        raise MODULE.ExternalCodexReturnError("foreign authorization binding")

    monkeypatch.setattr(MODULE, "_load_existing_authorization", reject_downstream)
    args = SimpleNamespace(
        return_owner=str(owner_path),
        handoff=str(handoff_path),
        holder_receipt=str(holder_path),
        authorization=str(authorization_path),
        closure_receipt=str(closure_path),
        return_receipt=str(return_path),
    )
    with pytest.raises(MODULE.ExternalCodexReturnError, match="foreign authorization"):
        MODULE._load_return_inputs(args)
    assert called is True


def test_lifecycle_outputs_may_not_alias() -> None:
    path = Path("/tmp/canonical-return.json")
    with pytest.raises(MODULE.ExternalCodexReturnError, match="aliases"):
        MODULE._validate_distinct_output_paths(
            [(path, "return receipt"), (path, "authorization")]
        )


def test_detached_return_follows_an_existing_live_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = {
        "owner_path": tmp_path / "owner.json",
        "handoff_path": tmp_path / "handoff.json",
        "holder_path": tmp_path / "holder.json",
        "authorization_path": tmp_path / "authorization.json",
        "closure_path": tmp_path / "closure.json",
        "return_path": tmp_path / "return.json",
    }
    inputs: dict[str, object] = {
        **paths,
        "owner_digest": "sha256:" + "1" * 64,
        "handoff_digest": "sha256:" + "2" * 64,
        "holder_digest": "sha256:" + "3" * 64,
    }
    detached_path = tmp_path / "detached.json"
    result_path = tmp_path / "result.json"
    log_path = tmp_path / "return.log"
    retry_detached = tmp_path / "detached.retry.json"
    retry_result = tmp_path / "result.retry.json"
    retry_log = tmp_path / "return.retry.log"
    original_binding = MODULE._detached_binding(
        inputs,
        detached_path=detached_path,
        result_path=result_path,
        log_path=log_path,
    )
    retry_binding = MODULE._detached_binding(
        inputs,
        detached_path=retry_detached,
        result_path=retry_result,
        log_path=retry_log,
    )
    original = {
        "schema_version": MODULE.DETACHED_SCHEMA_VERSION,
        "state": "stale",
        **original_binding,
        "retry_receipt_ref": str(retry_detached),
        "retry_result_ref": str(retry_result),
        "retry_log_ref": str(retry_log),
    }
    retry = {
        "schema_version": MODULE.DETACHED_SCHEMA_VERSION,
        "state": "running",
        "child_pid": 12345,
        "child_start_ticks": 67890,
        **retry_binding,
    }
    detached_path.write_bytes(MODULE._canonical_bytes(original) + b"\n")
    retry_detached.write_bytes(MODULE._canonical_bytes(retry) + b"\n")
    monkeypatch.setattr(MODULE.VISIBLE, "_proc_identity_state", lambda *_args: "live")
    monkeypatch.setattr(MODULE, "_load_return_inputs", lambda _args: inputs)
    args = SimpleNamespace(
        detach=True,
        return_receipt=str(paths["return_path"]),
        closure_receipt=str(paths["closure_path"]),
        detached_receipt=str(detached_path),
        detached_result=str(result_path),
        detached_log=str(log_path),
    )
    assert MODULE.command_return(args) == 0


def test_return_attempt_reuses_bound_receipt_path_after_alternate_retry(
    tmp_path: Path,
) -> None:
    paths = {
        "owner_path": tmp_path / "owner.json",
        "handoff_path": tmp_path / "handoff.json",
        "holder_path": tmp_path / "holder.json",
        "authorization_path": tmp_path / "authorization.json",
        "closure_path": tmp_path / "closure.json",
        "return_path": tmp_path / "return.json",
    }
    inputs: dict[str, object] = {
        **paths,
        "owner_digest": "sha256:" + "1" * 64,
        "handoff_digest": "sha256:" + "2" * 64,
        "holder_digest": "sha256:" + "3" * 64,
    }

    attempt_path, reservation = MODULE._reserve_return_attempt(inputs)
    assert reservation["return_receipt_ref"] == str(paths["return_path"].resolve())

    alternate = dict(inputs)
    alternate["return_path"] = tmp_path / "alternate-return.json"
    rebound = MODULE._bind_return_attempt(alternate)

    assert rebound["return_path"] == paths["return_path"]
    assert attempt_path == MODULE._return_attempt_path(paths["closure_path"])
    assert json.loads(attempt_path.read_text(encoding="utf-8"))["state"] == "reserved"


def test_output_reservation_rejects_relative_destination() -> None:
    with pytest.raises(MODULE.ExternalCodexReturnError, match="absolute"):
        MODULE._validate_output_path(Path("relative-receipt.json"), "return receipt")


def test_server_request_id_collision_is_not_treated_as_delivery_response() -> None:
    rpc = MODULE.UnixWebSocketRpc(Path("/run/user/1000/example.sock"))
    frames = iter(
        [
            (
                True,
                0x1,
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "server/request",
                        "params": {},
                    }
                ).encode("utf-8"),
            ),
            (
                True,
                0x1,
                b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}',
            ),
        ]
    )
    sent: list[dict[str, object]] = []
    rpc._recv_frame = lambda: next(frames)  # type: ignore[method-assign]
    rpc._send_json = lambda value: sent.append(value)  # type: ignore[method-assign]

    response = rpc._receive_json(1)

    assert response["result"] == {"ok": True}
    assert sent[0]["id"] == 1
    assert "error" in sent[0]


def test_json_rpc_response_requires_result() -> None:
    rpc = MODULE.UnixWebSocketRpc(Path("/run/user/1000/example.sock"))
    sent: list[dict[str, object]] = []
    rpc._send_json = lambda value: sent.append(value)  # type: ignore[method-assign]
    rpc._receive_json = lambda _request_id: {"id": 1}  # type: ignore[method-assign]
    with pytest.raises(MODULE.ExternalCodexReturnError, match="missing result"):
        rpc.call("turn/start")
    assert sent[0]["method"] == "turn/start"


def test_turn_delivery_requires_protocol_response_shape() -> None:
    assert MODULE._validate_turn_delivery(
        "turn/start",
        {"turn": {"id": "turn-1", "status": "inProgress"}},
    ) == {"turn_id": "turn-1", "status": "inProgress"}
    assert MODULE._validate_turn_delivery(
        "turn/steer", {"turnId": "turn-2"}
    ) == {"turn_id": "turn-2"}
    with pytest.raises(MODULE.ExternalCodexReturnError, match="did not return a Turn"):
        MODULE._validate_turn_delivery("turn/start", {})
    with pytest.raises(MODULE.ExternalCodexReturnError, match="did not return turnId"):
        MODULE._validate_turn_delivery("turn/steer", {})


@pytest.mark.parametrize("status", ["failed", "interrupted"])
def test_turn_delivery_rejects_terminal_failure_status(status: str) -> None:
    with pytest.raises(MODULE.ExternalCodexReturnError, match="accepted Turn"):
        MODULE._validate_turn_delivery(
            "turn/start",
            {"turn": {"id": "turn-failed", "status": status, "items": []}},
        )


def test_detached_retry_lock_is_stable_and_exclusive(tmp_path: Path) -> None:
    closure_path = tmp_path / "closure.json"
    retry_path = tmp_path / "return.json.detached.retry-1234"
    lock_path = closure_path.with_name(closure_path.name + ".return-attempt.lock")
    with MODULE._return_attempt_lock(closure_path):
        assert lock_path.is_file()
        assert not retry_path.with_name(retry_path.name + ".lock").exists()
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        competing_fd = os.open(lock_path, flags)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(competing_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(competing_fd)


@pytest.mark.parametrize("turns", [None, {}, {"unexpected": []}, "not-a-list"])
def test_active_turn_lookup_rejects_malformed_turn_list(turns: object) -> None:
    with pytest.raises(MODULE.ExternalCodexReturnError, match="invalid turns list"):
        MODULE._active_turn_id(turns)


def test_goal_binding_accepts_protocol_thread_only_identity() -> None:
    owner_value = MODULE.validate_return_owner(
        owner(
            goal="goal-external",
            thread="thread-transport",
            endpoint="unix:/run/user/1000/example.sock",
        )
    )
    assert MODULE._validate_goal_binding(
        {"threadId": "thread-transport", "status": "active"},
        owner_value,
    ) == "owner_goal_to_thread_binding"


def test_missing_retry_receipt_recovers_reserved_retry_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = {
        "owner_path": tmp_path / "owner.json",
        "handoff_path": tmp_path / "handoff.json",
        "holder_path": tmp_path / "holder.json",
        "authorization_path": tmp_path / "authorization.json",
        "closure_path": tmp_path / "closure.json",
        "return_path": tmp_path / "return.json",
    }
    inputs: dict[str, object] = {
        **paths,
        "owner_digest": "sha256:" + "1" * 64,
        "handoff_digest": "sha256:" + "2" * 64,
        "holder_digest": "sha256:" + "3" * 64,
    }
    detached_path = tmp_path / "detached.json"
    result_path = tmp_path / "result.json"
    log_path = tmp_path / "return.log"
    retry_detached = tmp_path / "detached.retry.json"
    retry_result = tmp_path / "result.retry.json"
    retry_log = tmp_path / "return.retry.log"
    binding = MODULE._detached_binding(
        inputs,
        detached_path=detached_path,
        result_path=result_path,
        log_path=log_path,
    )
    stale = {
        "schema_version": MODULE.DETACHED_SCHEMA_VERSION,
        "state": "stale",
        **binding,
        "retry_receipt_ref": str(retry_detached),
        "retry_result_ref": str(retry_result),
        "retry_log_ref": str(retry_log),
    }
    detached_path.write_bytes(MODULE._canonical_bytes(stale) + b"\n")
    monkeypatch.setattr(MODULE, "_load_return_inputs", lambda _args: inputs)
    monkeypatch.setattr(MODULE.VISIBLE, "_proc_identity_state", lambda *_args: "gone")
    monkeypatch.setattr(MODULE.os, "pipe", lambda: (0, 1))
    monkeypatch.setattr(
        MODULE.os,
        "fork",
        lambda: (_ for _ in ()).throw(AssertionError("launch-ready")),
    )
    args = SimpleNamespace(
        detach=True,
        return_receipt=str(paths["return_path"]),
        closure_receipt=str(paths["closure_path"]),
        detached_receipt=str(detached_path),
        detached_result=str(result_path),
        detached_log=str(log_path),
    )
    with pytest.raises(AssertionError, match="launch-ready"):
        MODULE.command_return(args)


def test_launch_reserved_orphan_log_transitions_to_recoverable_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = {
        "owner_path": tmp_path / "owner.json",
        "handoff_path": tmp_path / "handoff.json",
        "holder_path": tmp_path / "holder.json",
        "authorization_path": tmp_path / "authorization.json",
        "closure_path": tmp_path / "closure.json",
        "return_path": tmp_path / "return.json",
    }
    inputs: dict[str, object] = {
        **paths,
        "owner_digest": "sha256:" + "1" * 64,
        "handoff_digest": "sha256:" + "2" * 64,
        "holder_digest": "sha256:" + "3" * 64,
    }
    detached_path = tmp_path / "detached.json"
    result_path = tmp_path / "result.json"
    log_path = tmp_path / "return.log"
    binding = MODULE._detached_binding(
        inputs,
        detached_path=detached_path,
        result_path=result_path,
        log_path=log_path,
    )
    detached_path.write_bytes(
        MODULE._canonical_bytes(
            {
                "schema_version": MODULE.DETACHED_SCHEMA_VERSION,
                "state": "launch_reserved",
                "created_at": "2026-08-21T00:00:00Z",
                **binding,
            }
        )
        + b"\n"
    )
    log_path.write_text("orphaned launch\n", encoding="utf-8")
    monkeypatch.setattr(MODULE, "_load_return_inputs", lambda _args: inputs)
    monkeypatch.setattr(MODULE.VISIBLE, "_proc_identity_state", lambda *_args: "gone")
    monkeypatch.setattr(MODULE.os, "pipe", lambda: (0, 1))
    monkeypatch.setattr(
        MODULE.os,
        "fork",
        lambda: (_ for _ in ()).throw(AssertionError("launch-ready")),
    )
    args = SimpleNamespace(
        detach=True,
        return_receipt=str(paths["return_path"]),
        closure_receipt=str(paths["closure_path"]),
        detached_receipt=str(detached_path),
        detached_result=str(result_path),
        detached_log=str(log_path),
    )

    with pytest.raises(AssertionError, match="launch-ready"):
        MODULE.command_return(args)

    stale = json.loads(detached_path.read_text(encoding="utf-8"))
    assert stale["state"] == "stale"
    assert log_path.read_text(encoding="utf-8") == "orphaned launch\n"


def test_reusable_return_source_has_no_episode_coordinates() -> None:
    source = (PART / "external_codex_return.py").read_text(encoding="utf-8")
    for forbidden in (
        "019fbb8a-e084-7e73-9a98-647a1dd76985",
        "canonical-actor-return-lifecycle-luna-20260821",
        "wake_master_via_app_server.py",
    ):
        assert forbidden not in source


def test_owner_binding_requires_runtime_transport_and_acceptance_fields() -> None:
    invalid = {
        "schema_version": MODULE.RETURN_OWNER_SCHEMA_VERSION,
        "owner_id": "owner",
        "goal_id": "goal",
        "thread_id": "thread",
    }
    with pytest.raises(MODULE.ExternalCodexReturnError, match="owner_repo"):
        MODULE.validate_return_owner(invalid)
