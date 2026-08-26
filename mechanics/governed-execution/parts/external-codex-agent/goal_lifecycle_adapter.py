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
from typing import Any, Callable


RUNTIME_MODULE_NAME = "external_codex_return"
GOAL_TRANSITION_PROOF_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_transition_v1"
)
GOAL_TRANSITION_METHOD = "thread/goal/set"


class _RuntimeNamespace:
    """Attribute view over the already-executing runpy runtime namespace."""

    def __init__(self, namespace: dict[str, Any]) -> None:
        self._namespace = namespace

    def __getattr__(self, name: str) -> Any:
        try:
            return self._namespace[name]
        except KeyError as exc:  # pragma: no cover - broken install only
            raise AttributeError(name) from exc


_RUNTIME_NAMESPACE: dict[str, Any] | None = None


def bind_runtime_namespace(namespace: dict[str, Any]) -> None:
    """Bind the adapter to the runtime namespace that loaded it.

    Installed entrypoints execute ``external_codex_return.py`` with
    ``runpy.run_path``.  That namespace is not registered in ``sys.modules``;
    passing it here keeps the adapter's exception and helper identities
    identical to the executing runtime instead of loading a second module.
    """

    global _RUNTIME_NAMESPACE
    _RUNTIME_NAMESPACE = namespace


def _runtime() -> Any:
    if _RUNTIME_NAMESPACE is not None:
        return _RuntimeNamespace(_RUNTIME_NAMESPACE)
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


def _goal_attempt_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "external-codex-goal-lifecycle-attempt.schema.json"


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


def _attempt_path(receipt_path: Path) -> Path:
    runtime = _runtime()
    return runtime._validate_output_path(
        receipt_path.with_name(receipt_path.name + ".attempt.json"),
        "Goal lifecycle attempt reservation",
    )


def _attempt_binding(
    *,
    request: Any,
    decision: Any,
    owner: dict[str, Any],
    owner_path: Path,
    endpoint: Path,
    attempt_path: Path,
    precondition: dict[str, Any],
    content_ref_type: Any,
    canonical_digest: Callable[..., str],
) -> dict[str, Any]:
    runtime = _runtime()
    return {
        "schema_version": runtime.GOAL_LIFECYCLE_ATTEMPT_SCHEMA_VERSION,
        "state": "reserved",
        "attempt_id": f"goal-lifecycle-attempt:{request.idempotency_key}",
        "attempt_ref": str(attempt_path.resolve()),
        "reserved_at": runtime._utc_now(),
        "correlation_id": request.correlation_id,
        "idempotency_key": request.idempotency_key,
        "goal_ref": request.goal_ref.model_dump(mode="json"),
        "request_ref": decision.request_ref.model_dump(mode="json"),
        "decision_ref": _decision_ref(
            decision, content_ref_type, canonical_digest
        ).model_dump(mode="json"),
        "expected_state": request.expected_state,
        "desired_state": request.desired_state,
        "owner_ref": str(owner_path.resolve()),
        "owner_sha256": runtime._sha256_bytes(owner_path.read_bytes()),
        "owner": runtime._owner_projection(owner),
        "transport": {
            "kind": "codex_app_server_websocket_unix",
            "endpoint": str(endpoint),
        },
        "precondition": precondition,
    }


def _validate_attempt(
    value: dict[str, Any],
    *,
    request: Any,
    decision: Any,
    owner: dict[str, Any],
    owner_path: Path,
    endpoint: Path,
    attempt_path: Path,
) -> dict[str, Any]:
    runtime = _runtime()
    _load_schema(value, _goal_attempt_schema_path(), "Goal lifecycle attempt")
    content_ref_type, _decision_type, _execution_type, _request_type, _scope, _assert_receipt_scope, canonical_digest = _contract_types()
    expected_decision_ref = _decision_ref(
        decision, content_ref_type, canonical_digest
    ).model_dump(mode="json")
    if (
        value.get("attempt_ref") != str(attempt_path.resolve())
        or value.get("correlation_id") != request.correlation_id
        or value.get("idempotency_key") != request.idempotency_key
        or value.get("goal_ref") != request.goal_ref.model_dump(mode="json")
        or value.get("request_ref") != decision.request_ref.model_dump(mode="json")
        or value.get("decision_ref") != expected_decision_ref
        or value.get("owner_ref") != str(owner_path.resolve())
        or value.get("owner_sha256")
        != runtime._sha256_bytes(owner_path.read_bytes())
        or value.get("owner") != runtime._owner_projection(owner)
        or value.get("expected_state") != request.expected_state
        or value.get("desired_state") != request.desired_state
    ):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle attempt reservation is outside request/owner scope"
        )
    transport = value.get("transport")
    if (
        not isinstance(transport, dict)
        or transport.get("endpoint") != str(endpoint)
    ):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle attempt reservation endpoint mismatch"
        )
    return value


def _write_attempt(
    path: Path,
    value: dict[str, Any],
    *,
    request: Any,
    decision: Any,
    owner: dict[str, Any],
    owner_path: Path,
    endpoint: Path,
) -> dict[str, Any]:
    runtime = _runtime()
    _validate_attempt(
        value,
        request=request,
        decision=decision,
        owner=owner,
        owner_path=owner_path,
        endpoint=endpoint,
        attempt_path=path,
    )
    runtime._replace_json(path, value, "Goal lifecycle attempt reservation")
    return value


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
    mutation_response: dict[str, Any],
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
    response_digest = runtime._sha256_bytes(
        runtime._canonical_bytes(mutation_response)
    )
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
    mutation_response: dict[str, Any] | None,
    before_state: str,
    resulting_state: str,
    status: str,
    method: str,
    transition_request: dict[str, Any] | None,
    transition_proof: dict[str, Any] | None,
    attempt_path: Path | None,
    recovery: dict[str, Any] | None,
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
            "result_response": resulting_response,
            "before_response_sha256": runtime._sha256_bytes(
                runtime._canonical_bytes(before_response)
            ),
            "result_response_sha256": runtime._sha256_bytes(
                runtime._canonical_bytes(resulting_response)
            ),
            "mutation_response_sha256": (
                runtime._sha256_bytes(runtime._canonical_bytes(mutation_response))
                if mutation_response is not None
                else None
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
    if recovery is not None:
        receipt["lifecycle"]["recovery"] = recovery
    if attempt_path is not None and attempt_path.exists():
        receipt["attempt_artifact"] = {
            "ref": str(attempt_path.resolve()),
            "sha256": runtime._sha256_bytes(attempt_path.read_bytes()),
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
    attempt_path: Path | None = None,
    attempt: dict[str, Any] | None = None,
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
    if request.goal_ref.model_dump(mode="json") != owner.get("goal_ref"):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle request and transport owner Goal reference mismatch"
        )
    if request.return_owner_ref.model_dump(mode="json") != owner.get(
        "return_owner_ref"
    ):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle request and transport owner return-owner reference mismatch"
        )

    rpc_factory = rpc_factory or runtime.UnixWebSocketRpc
    mutation_response: dict[str, Any] | None = None
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
        precondition = _precondition(before_response, before_state)
        if attempt_path is not None:
            attempt_path = runtime._validate_output_path(
                attempt_path, "Goal lifecycle attempt reservation"
            )
        if attempt is not None:
            if attempt_path is None:
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle attempt reservation path is required"
                )
            _validate_attempt(
                attempt,
                request=request,
                decision=decision,
                owner=owner,
                owner_path=owner_path,
                endpoint=endpoint,
                attempt_path=attempt_path,
            )
        if (
            before_state == request.desired_state
            and attempt is not None
            and attempt.get("state") == "proof_recorded"
        ):
            stored_precondition = attempt.get("precondition")
            stored_response = attempt.get("goal_response")
            stored_proof = attempt.get("transition_proof")
            stored_request = attempt.get("transition_request")
            if (
                not isinstance(stored_precondition, dict)
                or not isinstance(stored_response, dict)
                or not isinstance(stored_proof, dict)
                or not isinstance(stored_request, dict)
            ):
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle attempt lacks complete mutation evidence"
                )
            _validated_transition_proof(
                stored_proof,
                owner=owner,
                precondition=stored_precondition,
                mutation_response=stored_response,
                request_frame=stored_request,
                from_state=request.expected_state,
                to_state=request.desired_state,
            )
            mutation_response = stored_response
            authoritative_response = before_response
            resulting_response = authoritative_response
            resulting_state = request.desired_state
            status = "executed"
            method = GOAL_TRANSITION_METHOD
            transition_request = stored_request
            transition_proof = stored_proof
            recovery = {
                "mode": "ambiguous_post_mutation",
                "mutation_response_available": True,
                "reconciled_by": "thread/goal/get",
                "authoritative": runtime._safe_response_summary(authoritative_response),
                "authoritative_response_sha256": runtime._sha256_bytes(
                    runtime._canonical_bytes(authoritative_response)
                ),
            }
            before_response = stored_precondition.get("goal_get_response")
            if not isinstance(before_response, dict):
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle attempt lacks its original precondition response"
                )
            before_state = request.expected_state
        elif before_state == request.desired_state and attempt is not None:
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle mutation reached its desired state without a complete durable transition proof"
            )
        elif before_state == request.desired_state:
            resulting_response = before_response
            resulting_state = before_state
            status = "replayed"
            method = "thread/goal/get"
            transition_request = None
            transition_proof = None
            recovery = None
        else:
            if before_state != request.expected_state:
                raise runtime.ExternalCodexReturnError(
                    "Codex app-server Goal state does not match the accepted "
                    "lifecycle precondition"
                )
            _require_atomic_adapter(rpc)
            if attempt_path is None:
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle mutation requires a durable attempt reservation"
                )
            if attempt is not None:
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle mutation already has a durable attempt; refusing to issue a second lifecycle set"
                )
            else:
                content_ref_type, _decision_type, _execution_type, _request_type, _scope, _assert_receipt_scope, canonical_digest = _contract_types()
                attempt = _attempt_binding(
                    request=request,
                    decision=decision,
                    owner=owner,
                    owner_path=owner_path,
                    endpoint=endpoint,
                    attempt_path=attempt_path,
                    precondition=precondition,
                    content_ref_type=content_ref_type,
                    canonical_digest=canonical_digest,
                )
                _write_attempt(
                    attempt_path,
                    attempt,
                    request=request,
                    decision=decision,
                    owner=owner,
                    owner_path=owner_path,
                    endpoint=endpoint,
                )

            def build_request_marker(
                method_name: str,
                params: dict[str, object] | None,
                request_id: int,
                payload: dict[str, object],
                timestamp_key: str,
            ) -> dict[str, Any]:
                if attempt is None or attempt_path is None:
                    raise runtime.ExternalCodexReturnError(
                        "Goal lifecycle mutation dispatch lacks a reservation"
                    )
                if (
                    method_name != GOAL_TRANSITION_METHOD
                    or not isinstance(params, dict)
                    or params.get("threadId") != owner["thread_id"]
                    or params.get("status") != request.desired_state
                ):
                    raise runtime.ExternalCodexReturnError(
                        "Goal lifecycle mutation dispatch identity mismatched"
                    )
                marker = {
                    "attempt_id": attempt["attempt_id"],
                    "method": method_name,
                    "request_id": request_id,
                    "params": params,
                    "params_sha256": runtime._sha256_bytes(
                        runtime._canonical_bytes(params)
                    ),
                    "request_sha256": runtime._sha256_bytes(
                        runtime._canonical_bytes(payload)
                    ),
                }
                marker[timestamp_key] = runtime._utc_now()
                return marker

            def record_request_prepared(
                method_name: str,
                params: dict[str, object] | None,
                request_id: int,
                payload: dict[str, object],
            ) -> None:
                if attempt is None or attempt_path is None:
                    return
                marker = build_request_marker(
                    method_name, params, request_id, payload, "reserved_at"
                )
                attempt["mutation_reserved"] = marker
                _write_attempt(
                    attempt_path,
                    attempt,
                    request=request,
                    decision=decision,
                    owner=owner,
                    owner_path=owner_path,
                    endpoint=endpoint,
                )

            def record_request_issued(
                method_name: str,
                params: dict[str, object] | None,
                request_id: int,
                payload: dict[str, object],
            ) -> None:
                if attempt is None or attempt_path is None:
                    return
                marker = build_request_marker(
                    method_name, params, request_id, payload, "issued_at"
                )
                attempt["state"] = "dispatched"
                attempt["mutation_dispatched"] = marker
                _write_attempt(
                    attempt_path,
                    attempt,
                    request=request,
                    decision=decision,
                    owner=owner,
                    endpoint=endpoint,
                    owner_path=owner_path,
                )

            previous_prepare_callback = getattr(rpc, "request_prepare_callback", None)
            previous_issued_callback = getattr(rpc, "request_issued_callback", None)
            setattr(rpc, "request_prepare_callback", record_request_prepared)
            setattr(rpc, "request_issued_callback", record_request_issued)
            try:
                result = rpc.atomic_goal_transition(
                    owner=owner,
                    precondition=precondition,
                    status=request.desired_state,
                )
            finally:
                setattr(rpc, "request_prepare_callback", previous_prepare_callback)
                setattr(rpc, "request_issued_callback", previous_issued_callback)
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
            mutation_response = resulting_response
            transition_proof = _validated_transition_proof(
                result.get("transition_proof"),
                owner=owner,
                precondition=precondition,
                mutation_response=mutation_response,
                request_frame=transition_request,
                from_state=request.expected_state,
                to_state=request.desired_state,
            )
            if attempt is not None and attempt_path is not None:
                mutation_dispatched = attempt.get("mutation_dispatched")
                if (
                    not isinstance(mutation_dispatched, dict)
                    or not isinstance(transition_request, dict)
                    or mutation_dispatched.get("request_id")
                    != transition_request.get("id")
                    or mutation_dispatched.get("request_sha256")
                    != transition_proof.get("request_sha256")
                ):
                    raise runtime.ExternalCodexReturnError(
                        "Goal lifecycle mutation returned without its durable dispatch marker"
                    )
                attempt["state"] = "proof_recorded"
                attempt["goal_response"] = resulting_response
                attempt["transition_request"] = transition_request
                attempt["transition_proof"] = transition_proof
                _write_attempt(
                    attempt_path,
                    attempt,
                    request=request,
                    decision=decision,
                    owner=owner,
                    owner_path=owner_path,
                    endpoint=endpoint,
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
            recovery = None
    return _execution_projection(
        request=request,
        decision=decision,
        owner=owner,
        owner_path=owner_path,
        endpoint=endpoint,
        initialize=initialize,
        before_response=before_response,
        resulting_response=resulting_response,
        mutation_response=mutation_response,
        before_state=before_state,
        resulting_state=resulting_state,
        status=status,
        method=method,
        transition_request=transition_request,
        transition_proof=transition_proof,
        attempt_path=attempt_path,
        recovery=recovery,
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
        attempt_path: Path | None = None,
        attempt: dict[str, Any] | None = None,
    ) -> None:
        self.owner = owner
        self.owner_path = owner_path
        self.endpoint = endpoint
        self.rpc_factory = rpc_factory
        self.attempt_path = attempt_path
        self.attempt = attempt

    def execute_goal_transition(self, request: Any, decision: Any) -> dict[str, Any]:
        return execute_goal_transition(
            request,
            decision,
            self.owner,
            self.owner_path,
            self.endpoint,
            rpc_factory=self.rpc_factory,
            attempt_path=self.attempt_path,
            attempt=self.attempt,
        )


def _validate_stored_transition_evidence(
    value: dict[str, Any],
    *,
    request: Any,
    owner: dict[str, Any],
) -> None:
    """Revalidate mutation and response digests before accepting a replay."""

    status = value.get("status")
    if status not in {"executed", "replayed"}:
        return
    runtime = _runtime()
    lifecycle = value.get("lifecycle")
    if not isinstance(lifecycle, dict):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt lacks mutation evidence"
        )
    result_digest = lifecycle.get("result_response_sha256")
    result_response = lifecycle.get("result_response")
    result_summary = lifecycle.get("result")
    if (
        not runtime._is_sha256_digest(result_digest)
        or not isinstance(result_response, dict)
        or not isinstance(result_summary, dict)
        or runtime._sha256_bytes(runtime._canonical_bytes(result_response))
        != result_digest
        or runtime._safe_response_summary(result_response) != result_summary
    ):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt authoritative result evidence is not bound"
        )
    if status != "executed":
        return
    before_digest = lifecycle.get("before_response_sha256")
    mutation_digest = lifecycle.get("mutation_response_sha256")
    request_frame = lifecycle.get("transition_request")
    proof = lifecycle.get("transition_proof")
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
    if (
        not runtime._is_sha256_digest(before_digest)
        or not runtime._is_sha256_digest(result_digest)
        or not runtime._is_sha256_digest(mutation_digest)
        or not isinstance(request_frame, dict)
        or set(request_frame) != {"jsonrpc", "id", "method", "params"}
        or request_frame.get("jsonrpc") != "2.0"
        or not isinstance(request_frame.get("id"), int)
        or isinstance(request_frame.get("id"), bool)
        or request_frame.get("id", 0) < 1
        or request_frame.get("method") != GOAL_TRANSITION_METHOD
        or not isinstance(request_frame.get("params"), dict)
        or request_frame["params"].get("threadId") != owner["thread_id"]
        or request_frame["params"].get("status") != request.desired_state
        or not isinstance(proof, dict)
        or set(proof) != expected_keys
        or proof.get("schema_version") != GOAL_TRANSITION_PROOF_SCHEMA_VERSION
        or proof.get("kind") != "server_compare_and_set"
        or proof.get("method") != GOAL_TRANSITION_METHOD
        or proof.get("thread_id") != owner["thread_id"]
        or proof.get("from_status") != request.expected_state
        or proof.get("to_status") != request.desired_state
        or proof.get("request_id") != request_frame.get("id")
        or not isinstance(proof.get("request_id"), int)
        or isinstance(proof.get("request_id"), bool)
        or proof.get("request_id", 0) < 1
        or proof.get("request_sha256")
        != runtime._sha256_bytes(runtime._canonical_bytes(request_frame))
        or proof.get("precondition_sha256") != before_digest
        or proof.get("goal_response_sha256") != mutation_digest
        or not runtime._is_sha256_digest(proof.get("precondition_sha256"))
        or not runtime._is_sha256_digest(proof.get("request_sha256"))
        or not runtime._is_sha256_digest(proof.get("goal_response_sha256"))
    ):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt transition evidence is not bound to its request and response"
        )
    recovery = lifecycle.get("recovery")
    if recovery is not None and (
        not isinstance(recovery, dict)
        or recovery.get("mode") != "ambiguous_post_mutation"
        or recovery.get("mutation_response_available") is not True
        or recovery.get("reconciled_by") != "thread/goal/get"
        or not isinstance(recovery.get("authoritative"), dict)
        or not runtime._is_sha256_digest(
            recovery.get("authoritative_response_sha256")
        )
        or recovery.get("authoritative_response_sha256") != result_digest
    ):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle recovery evidence is incomplete"
        )


def _validate_authoritative_result_response(
    value: dict[str, Any],
    *,
    response: dict[str, Any],
    owner: dict[str, Any],
) -> None:
    """Bind a replayed receipt to a fresh authoritative Goal read."""

    if value.get("status") not in {"executed", "replayed"}:
        return
    runtime = _runtime()
    lifecycle = value.get("lifecycle")
    if not isinstance(lifecycle, dict):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt lacks authoritative result evidence"
        )
    result_digest = lifecycle.get("result_response_sha256")
    if (
        not runtime._is_sha256_digest(result_digest)
        or runtime._sha256_bytes(runtime._canonical_bytes(response)) != result_digest
    ):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt authoritative result does not match the fresh Goal read"
        )
    goal = runtime._goal_object(response, "thread/goal/get")
    runtime._validate_goal_binding(goal, owner)
    state = runtime._string_at(goal, ("status",))
    if state != value.get("desired_state"):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt authoritative Goal state no longer matches"
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
    authoritative_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = _runtime()
    (
        content_ref_type,
        _decision_type,
        execution_type,
        _request_type,
        assert_scope,
        assert_receipt_scope,
        _digest,
    ) = _contract_types()
    assert_scope(request, decision)
    expected_decision_ref = _decision_ref(
        decision, content_ref_type, _digest
    )
    if value.get("receipt_ref") != str(path.resolve()):
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
        or parsed.decision_ref != expected_decision_ref
        or parsed.goal_ref != request.goal_ref
        or parsed.desired_state != request.desired_state
    ):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt does not match the request"
        )
    _validate_stored_transition_evidence(value, request=request, owner=owner)
    attempt_artifact = value.get("attempt_artifact")
    if value.get("status") == "executed" and attempt_artifact is None:
        raise runtime.ExternalCodexReturnError(
            "existing executed Goal lifecycle receipt requires a mutation attempt artifact"
        )
    if attempt_artifact is not None:
        if (
            not isinstance(attempt_artifact, dict)
            or not isinstance(attempt_artifact.get("ref"), str)
            or not runtime._is_sha256_digest(attempt_artifact.get("sha256"))
        ):
            raise runtime.ExternalCodexReturnError(
                "existing Goal lifecycle receipt attempt artifact is incomplete"
            )
        attempt_path = runtime._regular_file(
            Path(attempt_artifact["ref"]),
            "existing Goal lifecycle attempt reservation",
        )
        attempt_value, attempt_raw = runtime._load_json_file(
            attempt_path, "existing Goal lifecycle attempt reservation"
        )
        if (
            attempt_raw != runtime._canonical_bytes(attempt_value) + b"\n"
            or runtime._sha256_bytes(attempt_raw) != attempt_artifact["sha256"]
        ):
            raise runtime.ExternalCodexReturnError(
                "existing Goal lifecycle receipt attempt artifact digest mismatched"
            )
        _validate_attempt(
            attempt_value,
            request=request,
            decision=decision,
            owner=owner,
            owner_path=owner_path,
            endpoint=Path(value["transport"]["endpoint"]),
            attempt_path=attempt_path,
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
    if authoritative_response is not None:
        _validate_authoritative_result_response(
            value,
            response=authoritative_response,
            owner=owner,
        )
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
    attempt_path = _attempt_path(receipt_path)
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
    input_paths = {
        request_path.resolve(),
        decision_path.resolve(),
        owner_path.resolve(),
    }
    if {receipt_path.resolve(), attempt_path.resolve()} & input_paths:
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
            validated = _validate_existing_receipt(
                existing,
                request,
                decision,
                receipt_path,
                owner,
                owner_path,
                request_path,
                decision_path,
            )
            if validated.get("status") not in {"executed", "replayed"}:
                return validated
            endpoint, _resolution = runtime.discover_app_server_socket(owner)
            with runtime.UnixWebSocketRpc(endpoint) as rpc:
                runtime._initialize_rpc(rpc)
                authoritative_response = rpc.call(
                    "thread/goal/get",
                    {"threadId": owner["thread_id"]},
                )
            if not isinstance(authoritative_response, dict):
                raise runtime.ExternalCodexReturnError(
                    "Codex app-server Goal replay read returned a non-object"
                )
            return _validate_existing_receipt(
                validated,
                request,
                decision,
                receipt_path,
                owner,
                owner_path,
                request_path,
                decision_path,
                authoritative_response=authoritative_response,
            )
        attempt: dict[str, Any] | None = None
        if attempt_path.exists():
            attempt, attempt_raw = runtime._load_json_file(
                attempt_path, "existing Goal lifecycle attempt reservation"
            )
            if attempt_raw != runtime._canonical_bytes(attempt) + b"\n":
                raise runtime.ExternalCodexReturnError(
                    "existing Goal lifecycle attempt reservation is not canonically encoded"
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
            attempt_path=attempt_path,
            attempt=attempt,
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
        for path, expected, label in (
            (request_path, request_bytes, "Goal lifecycle request"),
            (decision_path, decision_bytes, "Goal lifecycle decision"),
            (owner_path, owner_bytes, "Goal lifecycle owner"),
        ):
            runtime.VISIBLE._assert_file_snapshot(path, expected, label)
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
