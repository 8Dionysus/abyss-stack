from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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


class FakeRpc:
    def __init__(self, endpoint: Path, *, active_turn: str | None) -> None:
        self.endpoint = endpoint
        self.active_turn = active_turn
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
        if method == "thread/goal/set":
            return {"goal": {"status": "active"}}
        if method == "thread/turns/list":
            if self.active_turn is None:
                return {"data": []}
            return {"data": [{"id": self.active_turn, "status": "inProgress"}]}
        if method in {"turn/start", "turn/steer"}:
            return {"turn": {"id": "new-turn", "status": "inProgress"}}
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
    assert any(method == expected_method for method, _params in fake.calls)


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
    receipt = MODULE.deliver_handoff(
        validated_owner,
        owner_path,
        handoff,
        tmp_path / "unused.sock",
        rpc_factory=lambda path: FakeRpc(path, active_turn=None),
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
