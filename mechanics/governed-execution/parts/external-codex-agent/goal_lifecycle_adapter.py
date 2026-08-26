"""Generic Goal lifecycle adapter for the current Codex app-server transport.

The caller supplies an owner-resolved ``GoalLifecycleRequest`` and an accepted
semantic ``GoalLifecycleDecision``.  This module only binds those objects to
the native app-server Goal API and confirms the resulting state with a fresh
read.  It does not decide whether a transition is legitimate.
"""

from __future__ import annotations

import contextlib
import fcntl
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


RUNTIME_MODULE_NAME = "external_codex_return"
GOAL_TRANSITION_PROOF_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_transition_v1"
)
GOAL_TRANSITION_METHOD = "thread/goal/set"


def _runtime() -> ModuleType:
    loaded = sys.modules.get(RUNTIME_MODULE_NAME)
    if loaded is not None:
        return loaded
    path = Path(__file__).with_name("external_codex_return.py")
    spec = importlib.util.spec_from_file_location(RUNTIME_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the sibling Codex runtime adapter")
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[RUNTIME_MODULE_NAME] = module
        spec.loader.exec_module(module)
        return module
    except (ImportError, OSError) as exc:  # pragma: no cover - broken install only
        sys.modules.pop(RUNTIME_MODULE_NAME, None)
        raise RuntimeError("cannot load the sibling Codex runtime adapter") from exc


def _contract_types() -> tuple[Any, ...]:
    try:
        from aoa_sdk.contracts.control_plane import ContentRef, canonical_digest
        from aoa_sdk.contracts.goal_lifecycle import (
            GoalLifecycleDecision,
            GoalLifecycleExecutionReceipt,
            GoalLifecycleRequest,
            assert_goal_lifecycle_execution_scope,
            assert_goal_lifecycle_execution_receipt_scope,
        )
    except ImportError as exc:  # pragma: no cover - install mismatch path
        raise _runtime().ExternalCodexReturnError(
            "generic Goal lifecycle requires the paired aoa-sdk goal lifecycle contract"
        ) from exc
    return (
        ContentRef,
        GoalLifecycleDecision,
        GoalLifecycleExecutionReceipt,
        GoalLifecycleRequest,
        assert_goal_lifecycle_execution_scope,
        assert_goal_lifecycle_execution_receipt_scope,
        canonical_digest,
    )


def _load_schema(value: dict[str, Any], path: Path, label: str) -> None:
    runtime = _runtime()
    try:
        schema = runtime.SCHEMA_VALIDATION.load_schema(path)
        error = runtime.SCHEMA_VALIDATION.first_error(value, schema)
    except runtime.SCHEMA_VALIDATION.SchemaValidationError as exc:
        raise runtime.ExternalCodexReturnError(f"{label} schema cannot be loaded") from exc
    if error is not None:
        raise runtime.ExternalCodexReturnError(f"{label} schema mismatch: {error}")


def _goal_owner_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "external-codex-goal-lifecycle-owner.schema.json"


def _goal_receipt_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "external-codex-goal-lifecycle-receipt.schema.json"


def _model(value: object, model_type: Any, label: str) -> Any:
    runtime = _runtime()
    try:
        return model_type.model_validate(value)
    except ValueError as exc:
        raise runtime.ExternalCodexReturnError(f"{label} is not a typed Goal lifecycle object") from exc


def _precondition(goal_response: dict[str, Any], state: str) -> dict[str, Any]:
    runtime = _runtime()
    summary = runtime._safe_response_summary(goal_response)
    return {
        "observed_state": state,
        "goal_get": summary,
        "goal_get_response": goal_response,
        "goal_get_summary_sha256": runtime._sha256_bytes(
            runtime._canonical_bytes(summary)
        ),
        "goal_response_sha256": runtime._sha256_bytes(
            runtime._canonical_bytes(goal_response)
        ),
    }


def _require_atomic_adapter(rpc: Any) -> None:
    runtime = _runtime()
    if getattr(rpc, "supports_atomic_goal_transition", False) is not True:
        raise runtime.ExternalCodexReturnError(
            "Codex app-server Goal adapter lacks a server-supported "
            "compare-and-set/version proof"
        )
    if not callable(getattr(rpc, "atomic_goal_transition", None)):
        raise runtime.ExternalCodexReturnError(
            "Codex app-server Goal adapter lacks atomic_goal_transition"
        )


def _validated_transition_proof(
    proof: object,
    *,
    owner: dict[str, Any],
    precondition: dict[str, Any],
    goal_response: dict[str, Any],
    request_frame: object,
    from_state: str,
    to_state: str,
) -> dict[str, Any]:
    runtime = _runtime()
    expected_keys = {
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
    }
    response_digest = runtime._sha256_bytes(runtime._canonical_bytes(goal_response))
    if not isinstance(proof, dict) or set(proof) != expected_keys:
        raise runtime.ExternalCodexReturnError(
            "Codex app-server Goal transition proof is incomplete"
        )
    if (
        not isinstance(request_frame, dict)
        or set(request_frame) != {"jsonrpc", "id", "method", "params"}
        or request_frame.get("jsonrpc") != "2.0"
        or not isinstance(request_frame.get("id"), int)
        or isinstance(request_frame.get("id"), bool)
        or request_frame.get("id", 0) < 1
        or request_frame.get("method") != GOAL_TRANSITION_METHOD
        or not isinstance(request_frame.get("params"), dict)
        or request_frame["params"].get("threadId") != owner["thread_id"]
        or request_frame["params"].get("status") != to_state
    ):
        raise runtime.ExternalCodexReturnError(
            "Codex app-server Goal transition request frame is not bound to "
            "the owner and requested state"
        )
    if (
        proof.get("schema_version") != GOAL_TRANSITION_PROOF_SCHEMA_VERSION
        or proof.get("kind") != "server_compare_and_set"
        or proof.get("method") != GOAL_TRANSITION_METHOD
        or proof.get("thread_id") != owner["thread_id"]
        or proof.get("from_status") != from_state
        or proof.get("to_status") != to_state
        or proof.get("precondition_sha256")
        != precondition["goal_response_sha256"]
        or not isinstance(proof.get("request_id"), int)
        or isinstance(proof.get("request_id"), bool)
        or proof.get("request_id", 0) < 1
        or not runtime._is_sha256_digest(proof.get("request_sha256"))
        or not runtime._is_sha256_digest(proof.get("precondition_sha256"))
        or proof.get("request_id") != request_frame.get("id")
        or proof.get("request_sha256")
        != runtime._sha256_bytes(runtime._canonical_bytes(request_frame))
        or proof.get("goal_response_sha256") != response_digest
    ):
        raise runtime.ExternalCodexReturnError(
            "Codex app-server Goal transition proof is not bound to the "
            "precondition, request, and resulting Goal"
        )
    return proof


def _decision_ref(decision: Any, content_ref_type: Any, canonical_digest: Callable[..., str]) -> Any:
    return content_ref_type(
        object_id=decision.decision_id,
        owner_repo=decision.resolved_by.owner_repo,
        schema_version=decision.schema_version,
        digest=canonical_digest(decision),
    )


def _execution_projection(
    *,
    request: Any,
    decision: Any,
    owner: dict[str, Any],
    owner_path: Path,
    endpoint: Path,
    initialize: dict[str, Any],
    before_response: dict[str, Any],
    resulting_response: dict[str, Any],
    before_state: str,
    resulting_state: str,
    status: str,
    method: str,
    transition_request: dict[str, Any] | None,
    transition_proof: dict[str, Any] | None,
) -> dict[str, Any]:
    runtime = _runtime()
    (
        content_ref_type,
        _decision_type,
        execution_type,
        _request_type,
        _scope,
        assert_receipt_scope,
        canonical_digest,
    ) = _contract_types()
    request_ref = decision.request_ref
    decision_ref = _decision_ref(decision, content_ref_type, canonical_digest)
    generated_at = runtime._utc_now()
    base = {
        "schema_version": runtime.GOAL_LIFECYCLE_RECEIPT_SCHEMA_VERSION,
        "execution_id": f"goal-transition-execution:{request.idempotency_key}",
        "stage": "executed",
        "correlation_id": request.correlation_id,
        "idempotency_key": request.idempotency_key,
        "goal_ref": request.goal_ref.model_dump(mode="json"),
        "request_ref": request_ref.model_dump(mode="json"),
        "decision_ref": decision_ref.model_dump(mode="json"),
        "observed_state": before_state,
        "desired_state": request.desired_state,
        "resulting_state": resulting_state,
        "status": status,
        "evidence_refs": [ref.model_dump(mode="json") for ref in request.evidence_refs],
        "produced_by": {
            "owner_repo": "abyss-stack",
            "artifact_ref": "mechanics/governed-execution/parts/external-codex-agent/goal_lifecycle_adapter.py",
            "source_ref": "goal-lifecycle-adapter",
            "artifact_digest": runtime._sha256_bytes(Path(__file__).read_bytes()),
            "schema_ref": "aoa_goal_lifecycle_v1",
            "schema_version": runtime.GOAL_LIFECYCLE_RECEIPT_SCHEMA_VERSION,
        },
        "executed_at": generated_at,
        "boundaries": {
            "requested": True,
            "accepted": True,
            "executed": True,
            "delivered": False,
            "semantically_accepted": False,
            "closed": False,
        },
    }
    typed_base = {
        **base,
        "schema_version": execution_type.model_fields["schema_version"].default,
    }
    typed_receipt = _model(
        typed_base, execution_type, "Goal lifecycle execution receipt"
    )
    assert_receipt_scope(request, decision, typed_receipt)
    receipt = {
        **base,
        "owner_ref": str(owner_path.resolve()),
        "owner_sha256": runtime._sha256_bytes(owner_path.read_bytes()),
        "owner": runtime._owner_projection(owner),
        "transport": {
            "kind": "codex_app_server_websocket_unix",
            "endpoint": str(endpoint),
            "method": method,
        },
        "lifecycle": {
            "initialize": runtime._safe_response_summary(initialize),
            "before": runtime._safe_response_summary(before_response),
            "result": runtime._safe_response_summary(resulting_response),
            "before_response_sha256": runtime._sha256_bytes(
                runtime._canonical_bytes(before_response)
            ),
            "result_response_sha256": runtime._sha256_bytes(
                runtime._canonical_bytes(resulting_response)
            ),
            "transition_request": transition_request,
            "transition_proof": transition_proof,
        },
        "owner_acceptance": "separate",
        "semantic_acceptance": "separate",
        "delivered": False,
        "closed": False,
        "generated_at": generated_at,
    }
    _load_schema(receipt, _goal_receipt_schema_path(), "Goal lifecycle receipt")
    return receipt


def execute_goal_transition(
    request: Any,
    decision: Any,
    owner: dict[str, Any],
    owner_path: Path,
    endpoint: Path,
    *,
    rpc_factory: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    """Execute one accepted semantic request through the Codex Goal API."""

    runtime = _runtime()
    (
        _content_ref_type,
        decision_type,
        _execution_type,
        request_type,
        assert_scope,
        _assert_receipt_scope,
        _canonical_digest,
    ) = _contract_types()
    request = _model(request, request_type, "Goal lifecycle request")
    decision = _model(decision, decision_type, "Goal lifecycle decision")
    assert_scope(request, decision)
    owner = runtime.validate_goal_lifecycle_owner(owner)
    _load_schema(owner, _goal_owner_schema_path(), "Goal lifecycle owner")
    if request.goal_ref.object_id != owner["goal_id"]:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle request and transport owner name different Goals"
        )
    if request.return_owner_ref.object_id != owner["owner_id"]:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle request and transport owner name different return owners"
        )

    rpc_factory = rpc_factory or runtime.UnixWebSocketRpc
    with rpc_factory(endpoint) as rpc:
        initialize = runtime._initialize_rpc(rpc)
        before_response = rpc.call(
            "thread/goal/get",
            {"threadId": owner["thread_id"]},
        )
        before_goal = runtime._goal_object(before_response, "thread/goal/get")
        runtime._validate_goal_binding(before_goal, owner)
        before_state = runtime._string_at(before_goal, ("status",))
        if before_state is None:
            raise runtime.ExternalCodexReturnError(
                "Codex app-server Goal read did not expose a state"
            )
        if before_state != request.expected_state:
            raise runtime.ExternalCodexReturnError(
                "Codex app-server Goal state does not match the accepted "
                "lifecycle precondition"
            )
        precondition = _precondition(before_response, before_state)
        if before_state == request.desired_state:
            resulting_response = before_response
            resulting_state = before_state
            status = "replayed"
            method = "thread/goal/get"
            transition_request = None
            transition_proof = None
        else:
            _require_atomic_adapter(rpc)
            result = rpc.atomic_goal_transition(
                owner=owner,
                precondition=precondition,
                status=request.desired_state,
            )
            if not isinstance(result, dict):
                raise runtime.ExternalCodexReturnError(
                    "Codex app-server Goal adapter returned a non-object transition"
                )
            resulting_response = result.get("goal_response")
            if not isinstance(resulting_response, dict):
                raise runtime.ExternalCodexReturnError(
                    "Codex app-server Goal adapter returned no Goal response"
                )
            transition_request = result.get("request_frame")
            transition_proof = _validated_transition_proof(
                result.get("transition_proof"),
                owner=owner,
                precondition=precondition,
                goal_response=resulting_response,
                request_frame=transition_request,
                from_state=request.expected_state,
                to_state=request.desired_state,
            )
            authoritative_response = rpc.call(
                "thread/goal/get",
                {"threadId": owner["thread_id"]},
            )
            authoritative_goal = runtime._goal_object(
                authoritative_response, "thread/goal/get"
            )
            runtime._validate_goal_binding(authoritative_goal, owner)
            authoritative_state = runtime._string_at(authoritative_goal, ("status",))
            if authoritative_state != request.desired_state:
                raise runtime.ExternalCodexReturnError(
                    "Codex app-server authoritative Goal read did not confirm "
                    "the requested lifecycle state"
                )
            resulting_response = authoritative_response
            resulting_state = authoritative_state
            status = "executed"
            method = GOAL_TRANSITION_METHOD
    return _execution_projection(
        request=request,
        decision=decision,
        owner=owner,
        owner_path=owner_path,
        endpoint=endpoint,
        initialize=initialize,
        before_response=before_response,
        resulting_response=resulting_response,
        before_state=before_state,
        resulting_state=resulting_state,
        status=status,
        method=method,
        transition_request=transition_request,
        transition_proof=transition_proof,
    )


class CodexGoalLifecycleAdapter:
    """Current-Codex adapter implementing the SDK lifecycle seam."""

    def __init__(
        self,
        *,
        owner: dict[str, Any],
        owner_path: Path,
        endpoint: Path,
        rpc_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self.owner = owner
        self.owner_path = owner_path
        self.endpoint = endpoint
        self.rpc_factory = rpc_factory

    def execute_goal_transition(self, request: Any, decision: Any) -> dict[str, Any]:
        return execute_goal_transition(
            request,
            decision,
            self.owner,
            self.owner_path,
            self.endpoint,
            rpc_factory=self.rpc_factory,
        )


def _validate_existing_receipt(
    value: dict[str, Any],
    request: Any,
    decision: Any,
    path: Path,
    owner: dict[str, Any],
    owner_path: Path,
    request_path: Path,
    decision_path: Path,
) -> dict[str, Any]:
    runtime = _runtime()
    (
        _content_ref_type,
        _decision_type,
        execution_type,
        _request_type,
        assert_scope,
        assert_receipt_scope,
        _digest,
    ) = _contract_types()
    assert_scope(request, decision)
    if value.get("receipt_ref") not in {None, str(path.resolve())}:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle receipt path identity mismatch"
        )
    projection = {
        key: value[key]
        for key in (
            "schema_version",
            "execution_id",
            "stage",
            "correlation_id",
            "idempotency_key",
            "goal_ref",
            "request_ref",
            "decision_ref",
            "observed_state",
            "desired_state",
            "resulting_state",
            "status",
            "evidence_refs",
            "produced_by",
            "executed_at",
            "boundaries",
        )
        if key in value
    }
    typed_projection = {
        **projection,
        "schema_version": execution_type.model_fields["schema_version"].default,
    }
    parsed = _model(
        typed_projection, execution_type, "existing Goal lifecycle receipt"
    )
    assert_receipt_scope(request, decision, parsed)
    if (
        parsed.correlation_id != request.correlation_id
        or parsed.idempotency_key != request.idempotency_key
        or parsed.request_ref != decision.request_ref
        or parsed.goal_ref != request.goal_ref
        or parsed.desired_state != request.desired_state
    ):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt does not match the request"
        )
    if (
        value.get("owner_ref") != str(owner_path.resolve())
        or value.get("owner_sha256") != runtime._sha256_bytes(owner_path.read_bytes())
        or value.get("owner") != runtime._owner_projection(owner)
    ):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt does not match the owner binding"
        )
    for field, expected_path, label in (
        ("request_artifact", request_path, "request"),
        ("decision_artifact", decision_path, "decision"),
    ):
        artifact = value.get(field)
        if (
            not isinstance(artifact, dict)
            or artifact.get("ref") != str(expected_path.resolve())
            or artifact.get("sha256")
            != runtime._sha256_bytes(expected_path.read_bytes())
        ):
            raise runtime.ExternalCodexReturnError(
                f"existing Goal lifecycle receipt does not match the {label} artifact"
            )
    _load_schema(value, _goal_receipt_schema_path(), "Goal lifecycle receipt")
    return value


@contextlib.contextmanager
def _attempt_lock(path: Path):
    runtime = _runtime()
    lock_path = path.with_name(path.name + ".goal-lifecycle.lock")
    runtime._validate_output_path(lock_path, "Goal lifecycle attempt lock")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise runtime.ExternalCodexReturnError(
            f"cannot open Goal lifecycle attempt lock: {lock_path}"
        ) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle attempt lock failed: {lock_path}"
        ) from exc
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def run_goal_transition(args: Any) -> dict[str, Any]:
    """Load owner-semantic artifacts and run the generic adapter leaf."""

    runtime = _runtime()
    (
        _content_ref_type,
        _decision_type,
        _execution_type,
        request_type,
        assert_scope,
        _assert_receipt_scope,
        _canonical_digest,
    ) = _contract_types()
    request_path = runtime._regular_file(Path(args.request), "Goal lifecycle request")
    decision_path = runtime._regular_file(Path(args.decision), "Goal lifecycle decision")
    owner_path = runtime._regular_file(Path(args.owner), "Goal lifecycle owner")
    receipt_path = runtime._validate_output_path(
        Path(args.receipt), "Goal lifecycle receipt"
    )
    request_value, request_bytes = runtime._load_json_file(
        request_path, "Goal lifecycle request"
    )
    decision_value, decision_bytes = runtime._load_json_file(
        decision_path, "Goal lifecycle decision"
    )
    owner_value, owner_bytes = runtime._load_json_file(
        owner_path, "Goal lifecycle owner"
    )
    request = _model(request_value, request_type, "Goal lifecycle request")
    decision = _model(decision_value, _decision_type, "Goal lifecycle decision")
    assert_scope(request, decision)
    owner = runtime.validate_goal_lifecycle_owner(owner_value)
    if receipt_path.resolve() in {
        request_path.resolve(),
        decision_path.resolve(),
        owner_path.resolve(),
    }:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle receipt must be distinct from all input artifacts"
        )
    with _attempt_lock(receipt_path):
        if receipt_path.exists():
            existing, raw = runtime._load_json_file(
                receipt_path, "existing Goal lifecycle receipt"
            )
            if raw != runtime._canonical_bytes(existing) + b"\n":
                raise runtime.ExternalCodexReturnError(
                    "existing Goal lifecycle receipt is not canonically encoded"
                )
            return _validate_existing_receipt(
                existing,
                request,
                decision,
                receipt_path,
                owner,
                owner_path,
                request_path,
                decision_path,
            )
        runtime.VISIBLE._assert_file_snapshot(
            request_path, request_bytes, "Goal lifecycle request"
        )
        runtime.VISIBLE._assert_file_snapshot(
            decision_path, decision_bytes, "Goal lifecycle decision"
        )
        runtime.VISIBLE._assert_file_snapshot(owner_path, owner_bytes, "Goal lifecycle owner")
        endpoint, resolution = runtime.discover_app_server_socket(owner)
        receipt = CodexGoalLifecycleAdapter(
            owner=owner,
            owner_path=owner_path,
            endpoint=endpoint,
        ).execute_goal_transition(
            request, decision
        )
        receipt["receipt_ref"] = str(receipt_path.resolve())
        receipt["transport"]["resolution"] = resolution
        receipt["request_ref"] = decision.request_ref.model_dump(mode="json")
        receipt["request_artifact"] = {
            "ref": str(request_path.resolve()),
            "sha256": runtime._sha256_bytes(request_bytes),
        }
        receipt["decision_artifact"] = {
            "ref": str(decision_path.resolve()),
            "sha256": runtime._sha256_bytes(decision_bytes),
        }
        runtime._replace_json(receipt_path, receipt, "Goal lifecycle receipt")
        runtime.VISIBLE._assert_file_snapshot(owner_path, owner_bytes, "Goal lifecycle owner")
        return _validate_existing_receipt(
            receipt,
            request,
            decision,
            receipt_path,
            owner,
            owner_path,
            request_path,
            decision_path,
        )
