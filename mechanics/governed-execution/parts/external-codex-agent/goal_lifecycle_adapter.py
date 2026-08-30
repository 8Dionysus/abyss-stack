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
import pwd
import stat
import sys
from pathlib import Path
from typing import Any, Callable


RUNTIME_MODULE_NAME = "external_codex_return"
GOAL_TRANSITION_PROOF_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_transition_v2"
)
LEGACY_GOAL_TRANSITION_PROOF_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_transition_v1"
)
GOAL_TRANSITION_METHOD = "thread/goal/set"
LEGACY_SEMANTIC_ATTEMPT_ANCHOR_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_lifecycle_attempt_anchor_v1"
)
SEMANTIC_ATTEMPT_ANCHOR_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_lifecycle_attempt_anchor_v2"
)


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


def _validated_read_only_precondition(
    value: object,
    *,
    owner: dict[str, Any],
    desired_state: str,
) -> dict[str, Any]:
    """Validate the durable observation that completed a no-mutation attempt."""

    runtime = _runtime()
    if not isinstance(value, dict):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle read-only attempt lacks its durable observation"
        )
    response = value.get("goal_get_response")
    summary = value.get("goal_get")
    if (
        value.get("observed_state") != desired_state
        or not isinstance(response, dict)
        or not isinstance(summary, dict)
        or value.get("goal_response_sha256")
        != runtime._sha256_bytes(runtime._canonical_bytes(response))
        or runtime._safe_response_summary(response) != summary
        or value.get("goal_get_summary_sha256")
        != runtime._sha256_bytes(runtime._canonical_bytes(summary))
    ):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle read-only attempt observation is not bound"
        )
    _validate_stored_goal_response(
        response,
        owner=owner,
        expected_state=desired_state,
        method="thread/goal/get",
        label="read-only completion",
    )
    return response


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
    owner_bytes: bytes,
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
        "owner_sha256": runtime._sha256_bytes(owner_bytes),
        "owner": runtime._owner_projection(owner),
        "transport": {
            "kind": "codex_app_server_websocket_unix",
            "endpoint": str(endpoint),
        },
        "precondition": precondition,
    }


def _validate_attempt_marker(
    value: object,
    *,
    label: str,
    attempt_id: str,
    owner: dict[str, Any],
    desired_state: str,
    timestamp_key: str,
) -> dict[str, Any]:
    """Validate a durable request marker before trusting a recovery attempt."""

    runtime = _runtime()
    if not isinstance(value, dict):
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle {label} dispatch marker is missing"
        )
    expected_keys = {
        "attempt_id",
        "method",
        "request_id",
        "params",
        "params_sha256",
        "request_sha256",
        timestamp_key,
    }
    if set(value) != expected_keys:
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle {label} dispatch marker is incomplete"
        )
    request_id = value.get("request_id")
    params = value.get("params")
    if (
        value.get("attempt_id") != attempt_id
        or value.get("method") != GOAL_TRANSITION_METHOD
        or not isinstance(request_id, int)
        or isinstance(request_id, bool)
        or request_id < 1
        or not isinstance(params, dict)
        or params.get("threadId") != owner["thread_id"]
        or params.get("status") != desired_state
        or not isinstance(value.get(timestamp_key), str)
        or not value.get(timestamp_key)
        or not runtime._is_sha256_digest(value.get("params_sha256"))
        or value.get("params_sha256")
        != runtime._sha256_bytes(runtime._canonical_bytes(params))
    ):
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle {label} dispatch marker is not bound to the requested Goal"
        )
    request_frame = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": GOAL_TRANSITION_METHOD,
        "params": params,
    }
    if (
        not runtime._is_sha256_digest(value.get("request_sha256"))
        or value.get("request_sha256")
        != runtime._sha256_bytes(runtime._canonical_bytes(request_frame))
    ):
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle {label} dispatch marker request digest is not bound"
        )
    return value


def _validate_attempt_markers(
    value: dict[str, Any],
    *,
    owner: dict[str, Any],
    desired_state: str,
) -> None:
    """Enforce marker presence and identity for each durable attempt state."""

    runtime = _runtime()
    state = value.get("state")
    attempt_id = value.get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle attempt reservation lacks an attempt identity"
        )
    reserved = value.get("mutation_reserved")
    dispatched = value.get("mutation_dispatched")
    if state in {"reserved", "read_only_recorded"}:
        if dispatched is not None:
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle non-dispatched attempt contains a dispatch marker"
            )
        if state == "read_only_recorded" and reserved is not None:
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle read-only attempt contains a mutation reservation"
            )
        if reserved is not None:
            _validate_attempt_marker(
                reserved,
                label="reservation",
                attempt_id=attempt_id,
                owner=owner,
                desired_state=desired_state,
                timestamp_key="reserved_at",
            )
        return
    if state not in {"dispatched", "proof_recorded"}:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle attempt reservation has an unsupported state"
        )
    reserved_marker = _validate_attempt_marker(
        reserved,
        label="reservation",
        attempt_id=attempt_id,
        owner=owner,
        desired_state=desired_state,
        timestamp_key="reserved_at",
    )
    dispatched_marker = _validate_attempt_marker(
        dispatched,
        label="issued",
        attempt_id=attempt_id,
        owner=owner,
        desired_state=desired_state,
        timestamp_key="issued_at",
    )
    for key in ("request_id", "params_sha256", "request_sha256"):
        if reserved_marker.get(key) != dispatched_marker.get(key):
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle dispatch markers do not describe the same request"
            )
    if reserved_marker.get("params") != dispatched_marker.get("params"):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle dispatch markers do not describe the same parameters"
        )


def _request_frame_from_marker(marker: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": marker["request_id"],
        "method": marker["method"],
        "params": marker["params"],
    }


def _validate_attempt(
    value: dict[str, Any],
    *,
    request: Any,
    decision: Any,
    owner: dict[str, Any],
    owner_path: Path,
    owner_bytes: bytes,
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
        or value.get("owner_sha256") != runtime._sha256_bytes(owner_bytes)
        or value.get("owner") != runtime._owner_projection(owner)
        or value.get("expected_state") != request.expected_state
        or value.get("desired_state") != request.desired_state
    ):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle attempt reservation is outside request/owner scope"
        )
    transport = value.get("transport")
    stored_endpoint = transport.get("endpoint") if isinstance(transport, dict) else None
    if not isinstance(stored_endpoint, str):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle attempt reservation endpoint mismatch"
        )
    runtime._socket_path(stored_endpoint)
    if (
        owner.get("transport_posture")
        != "resolve-current-local-codex-app-server"
        and stored_endpoint != str(endpoint)
    ):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle attempt reservation endpoint mismatch"
        )
    _validate_attempt_markers(
        value,
        owner=owner,
        desired_state=request.desired_state,
    )
    if value.get("state") == "read_only_recorded":
        _validated_read_only_precondition(
            value.get("precondition"),
            owner=owner,
            desired_state=request.desired_state,
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
    owner_bytes: bytes,
    endpoint: Path,
) -> dict[str, Any]:
    runtime = _runtime()
    _validate_attempt(
        value,
        request=request,
        decision=decision,
        owner=owner,
        owner_path=owner_path,
        owner_bytes=owner_bytes,
        endpoint=endpoint,
        attempt_path=path,
    )
    runtime._replace_json(path, value, "Goal lifecycle attempt reservation")
    _mark_semantic_attempt_started(request, owner, path)
    return value


def _validated_transition_proof(
    proof: object,
    *,
    owner: dict[str, Any],
    precondition: dict[str, Any],
    mutation_response: dict[str, Any] | None,
    expected_mutation_response_digest: object | None = None,
    post_read_response: dict[str, Any] | None,
    request_frame: object,
    from_state: str,
    to_state: str,
) -> dict[str, Any]:
    runtime = _runtime()
    if not isinstance(proof, dict):
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
    mutation_response_available = mutation_response is not None or runtime._is_sha256_digest(
        expected_mutation_response_digest
    )
    response_digest = (
        runtime._sha256_bytes(runtime._canonical_bytes(mutation_response))
        if mutation_response is not None
        else expected_mutation_response_digest
    )
    if (
        expected_mutation_response_digest is not None
        and mutation_response is not None
        and response_digest != expected_mutation_response_digest
    ):
        raise runtime.ExternalCodexReturnError(
            "Codex app-server Goal transition response digest is not bound"
        )
    if proof.get("schema_version") == LEGACY_GOAL_TRANSITION_PROOF_SCHEMA_VERSION:
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
        if not runtime._is_sha256_digest(response_digest):
            raise runtime.ExternalCodexReturnError(
                "legacy Goal transition proof lacks its mutation response"
            )
        if (
            set(proof) != expected_keys
            or proof.get("kind") != "server_compare_and_set"
            or proof.get("method") != GOAL_TRANSITION_METHOD
            or proof.get("thread_id") != owner["thread_id"]
            or proof.get("from_status") != from_state
            or proof.get("to_status") != to_state
            or proof.get("precondition_sha256")
            != precondition["goal_response_sha256"]
            or proof.get("request_id") != request_frame.get("id")
            or not runtime._is_sha256_digest(proof.get("request_sha256"))
            or proof.get("request_sha256")
            != runtime._sha256_bytes(runtime._canonical_bytes(request_frame))
            or proof.get("goal_response_sha256") != response_digest
        ):
            raise runtime.ExternalCodexReturnError(
                "legacy Goal transition proof is not bound to its request and response"
            )
        return proof
    if not isinstance(post_read_response, dict):
        raise runtime.ExternalCodexReturnError(
            "Codex app-server Goal transition evidence lacks a post-read"
        )
    post_read_digest = runtime._sha256_bytes(
        runtime._canonical_bytes(post_read_response)
    )
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
        "post_read_response_sha256",
        "response_available",
    }
    if (
        set(proof) != expected_keys
        or proof.get("schema_version") != GOAL_TRANSITION_PROOF_SCHEMA_VERSION
        or proof.get("kind")
        != (
            "request_response_post_read"
            if mutation_response_available
            else "dispatch_reconciled_post_read"
        )
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
        or proof.get("post_read_response_sha256") != post_read_digest
        or proof.get("response_available") is not mutation_response_available
    ):
        raise runtime.ExternalCodexReturnError(
            "Codex app-server Goal transition evidence is not bound to the "
            "precondition, request, response, and post-read"
        )
    return proof


def _transition_proof(
    *,
    owner: dict[str, Any],
    precondition: dict[str, Any],
    mutation_response: dict[str, Any] | None,
    post_read_response: dict[str, Any],
    request_frame: dict[str, Any],
    from_state: str,
    to_state: str,
) -> dict[str, Any]:
    runtime = _runtime()
    proof = {
        "schema_version": GOAL_TRANSITION_PROOF_SCHEMA_VERSION,
        "kind": (
            "request_response_post_read"
            if mutation_response is not None
            else "dispatch_reconciled_post_read"
        ),
        "method": GOAL_TRANSITION_METHOD,
        "thread_id": owner["thread_id"],
        "from_status": from_state,
        "to_status": to_state,
        "precondition_sha256": precondition["goal_response_sha256"],
        "request_id": request_frame["id"],
        "request_sha256": runtime._sha256_bytes(
            runtime._canonical_bytes(request_frame)
        ),
        "goal_response_sha256": (
            runtime._sha256_bytes(runtime._canonical_bytes(mutation_response))
            if mutation_response is not None
            else None
        ),
        "post_read_response_sha256": runtime._sha256_bytes(
            runtime._canonical_bytes(post_read_response)
        ),
        "response_available": mutation_response is not None,
    }
    return _validated_transition_proof(
        proof,
        owner=owner,
        precondition=precondition,
        mutation_response=mutation_response,
        post_read_response=post_read_response,
        request_frame=request_frame,
        from_state=from_state,
        to_state=to_state,
    )


def _validate_stored_goal_response(
    response: object,
    *,
    owner: dict[str, Any],
    expected_state: str,
    method: str,
    label: str,
) -> dict[str, Any]:
    """Validate a stored raw Goal response before using it as evidence."""

    runtime = _runtime()
    if not isinstance(response, dict):
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle stored {label} response is not an object"
        )
    goal = runtime._goal_object(response, method)
    runtime._validate_goal_binding(goal, owner)
    state = runtime._string_at(goal, ("status",))
    if state != expected_state:
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle stored {label} response does not confirm "
            f"state {expected_state!r}"
        )
    return goal


def _decision_ref(decision: Any, content_ref_type: Any, canonical_digest: Callable[..., str]) -> Any:
    return content_ref_type(
        object_id=decision.decision_id,
        owner_repo=decision.resolved_by.owner_repo,
        schema_version=decision.schema_version,
        digest=canonical_digest(decision),
    )


def _resolve_owner_endpoint(
    owner: dict[str, Any],
    supplied_endpoint: Path,
    *,
    rpc_factory: Callable[[Path], Any] | None,
) -> Path:
    """Resolve and bind the transport endpoint before opening any RPC."""

    runtime = _runtime()
    supplied = runtime._socket_path(str(supplied_endpoint))
    owner_endpoint = runtime._endpoint_from_owner(owner)
    if owner_endpoint is not None:
        resolved = runtime._socket_path(owner_endpoint)
        if supplied != resolved:
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle supplied endpoint does not match the owner-bound endpoint"
            )
        return resolved
    resolved, _resolution = runtime.discover_app_server_socket(
        owner,
        rpc_factory=rpc_factory,
    )
    return runtime._socket_path(str(resolved))


def _validate_request_owner_scope(request: Any, owner: dict[str, Any]) -> None:
    """Bind the typed request's qualified references to the selected owner."""

    runtime = _runtime()
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


def _execution_projection(
    *,
    request: Any,
    decision: Any,
    owner: dict[str, Any],
    owner_path: Path,
    owner_bytes: bytes,
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
        # The typed receipt remains bound to the accepted request's
        # observation. A duplicate invocation may read the already-desired
        # state after another caller completed the same semantic attempt; the
        # fresh state remains visible in lifecycle.before/result evidence.
        "observed_state": request.observed_state,
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
        "owner_sha256": runtime._sha256_bytes(owner_bytes),
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


def _require_supplied_attempt_artifact(
    path: Path,
    supplied_attempt: dict[str, Any],
) -> dict[str, Any]:
    """Require an SDK recovery hint to match its durable canonical sidecar."""

    runtime = _runtime()
    if not path.exists():
        raise runtime.ExternalCodexReturnError(
            "supplied Goal lifecycle attempt requires its durable artifact"
        )
    stored_attempt, stored_raw = runtime._load_json_file(
        path, "existing Goal lifecycle attempt reservation"
    )
    if stored_raw != runtime._canonical_bytes(stored_attempt) + b"\n":
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle attempt reservation is not canonically encoded"
        )
    if supplied_attempt != stored_attempt:
        raise runtime.ExternalCodexReturnError(
            "supplied Goal lifecycle attempt does not match its durable artifact"
        )
    return stored_attempt


def _execute_goal_transition_unlocked(
    request: Any,
    decision: Any,
    owner: dict[str, Any],
    owner_path: Path,
    endpoint: Path,
    *,
    rpc_factory: Callable[[Path], Any] | None = None,
    attempt_path: Path | None = None,
    attempt: dict[str, Any] | None = None,
    endpoint_is_owner_resolved: bool = False,
    artifact_snapshots: tuple[tuple[Path, bytes, str], ...] = (),
) -> dict[str, Any]:
    """Execute one accepted semantic request while the attempt lock is held."""

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
    owner_path = runtime._regular_file(Path(owner_path), "Goal lifecycle owner")
    owner_artifact, owner_bytes = runtime._load_json_file(
        owner_path, "Goal lifecycle owner"
    )
    owner = runtime.validate_goal_lifecycle_owner(owner)
    owner_artifact = runtime.validate_goal_lifecycle_owner(owner_artifact)
    if owner_artifact != owner:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle owner artifact does not match the supplied owner"
        )
    _load_schema(owner, _goal_owner_schema_path(), "Goal lifecycle owner")
    _validate_request_owner_scope(request, owner)

    if endpoint_is_owner_resolved:
        endpoint = runtime._socket_path(str(endpoint))
    else:
        endpoint = _resolve_owner_endpoint(
            owner,
            Path(endpoint),
            rpc_factory=rpc_factory,
        )
    if attempt_path is not None:
        attempt_path = runtime._validate_output_path(
            attempt_path, "Goal lifecycle attempt reservation"
        )
        if attempt is not None:
            attempt = _require_supplied_attempt_artifact(attempt_path, attempt)
        elif attempt_path.exists():
            stored_attempt, stored_raw = runtime._load_json_file(
                attempt_path, "existing Goal lifecycle attempt reservation"
            )
            if stored_raw != runtime._canonical_bytes(stored_attempt) + b"\n":
                raise runtime.ExternalCodexReturnError(
                    "existing Goal lifecycle attempt reservation is not canonically encoded"
                )
            attempt = stored_attempt
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
            owner_bytes=owner_bytes,
            endpoint=endpoint,
            attempt_path=attempt_path,
        )
        _mark_semantic_attempt_started(request, owner, attempt_path)

    rpc_factory = rpc_factory or runtime.UnixWebSocketRpc
    mutation_response: dict[str, Any] | None = None
    resulting_response: dict[str, Any]
    resulting_state: str
    status: str
    method: str
    transition_request: dict[str, Any] | None = None
    transition_proof: dict[str, Any] | None = None
    recovery: dict[str, Any] | None = None
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
        if (
            before_state == request.desired_state
            and attempt is not None
            and attempt.get("state") == "proof_recorded"
        ):
            stored_precondition = attempt.get("precondition")
            stored_response = attempt.get("goal_response")
            stored_post_read = attempt.get("post_read_response")
            stored_proof = attempt.get("transition_proof")
            stored_request = attempt.get("transition_request")
            if (
                not isinstance(stored_precondition, dict)
                or not isinstance(stored_proof, dict)
                or not isinstance(stored_request, dict)
            ):
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle attempt lacks complete mutation evidence"
                )
            proof_is_current = (
                stored_proof.get("schema_version")
                == GOAL_TRANSITION_PROOF_SCHEMA_VERSION
            )
            _validate_stored_goal_response(
                stored_precondition.get("goal_get_response"),
                owner=owner,
                expected_state=request.expected_state,
                method="thread/goal/get",
                label="precondition",
            )
            if proof_is_current:
                if not isinstance(stored_post_read, dict):
                    raise runtime.ExternalCodexReturnError(
                        "Goal lifecycle v2 attempt lacks its stored post-read response"
                    )
                proof_post_read = stored_post_read
                _validate_stored_goal_response(
                    proof_post_read,
                    owner=owner,
                    expected_state=request.desired_state,
                    method="thread/goal/get",
                    label="post-read",
                )
            else:
                # Legacy v1 proofs had no independently bound post-read.  The
                # mutation response is their only historical result, so use it
                # consistently for validation and receipt projection.
                if not isinstance(stored_response, dict):
                    raise runtime.ExternalCodexReturnError(
                        "Goal lifecycle legacy attempt lacks its mutation response"
                    )
                proof_post_read = stored_response
            if isinstance(stored_response, dict):
                _validate_stored_goal_response(
                    stored_response,
                    owner=owner,
                    expected_state=request.desired_state,
                    method=GOAL_TRANSITION_METHOD,
                    label="mutation",
                )
            _validated_transition_proof(
                stored_proof,
                owner=owner,
                precondition=stored_precondition,
                mutation_response=stored_response,
                post_read_response=proof_post_read,
                request_frame=stored_request,
                from_state=request.expected_state,
                to_state=request.desired_state,
            )
            mutation_response = stored_response
            # The fresh read above is only a current-state check.  Preserve
            # the post-read that was already bound into the durable proof so
            # a metadata-only change cannot rewrite the historical receipt
            # or make the attempt/receipt bindings disagree.
            authoritative_response = (
                proof_post_read if proof_is_current else before_response
            )
            if not proof_is_current and isinstance(stored_response, dict):
                # Legacy proofs had no separate post-read field.  The
                # receipt-attempt binding treats their mutation response as
                # the historical result, so project that same response
                # rather than combining the legacy proof with a fresh read.
                authoritative_response = stored_response
            resulting_response = authoritative_response
            resulting_state = request.desired_state
            status = "executed"
            method = GOAL_TRANSITION_METHOD
            transition_request = stored_request
            transition_proof = stored_proof
            recovery = {
                "mode": "ambiguous_post_mutation",
                "mutation_response_available": isinstance(stored_response, dict),
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
        elif (
            before_state == request.desired_state
            and attempt is not None
            and attempt.get("state") == "read_only_recorded"
        ):
            stored_read = _validated_read_only_precondition(
                attempt.get("precondition"),
                owner=owner,
                desired_state=request.desired_state,
            )
            # The fresh read is a current-state check. Preserve the original
            # read-only completion bytes in every replayed receipt.
            before_response = stored_read
            before_state = request.desired_state
            resulting_response = stored_read
            resulting_state = request.desired_state
            status = "replayed"
            method = "thread/goal/get"
            transition_request = None
            transition_proof = None
            recovery = None
        elif before_state == request.desired_state and attempt is not None:
            if attempt.get("state") != "dispatched":
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle mutation reached its desired state without a complete durable transition proof"
                )
            stored_precondition = attempt.get("precondition")
            mutation_dispatched = attempt.get("mutation_dispatched")
            stored_response = attempt.get("goal_response")
            if not isinstance(stored_precondition, dict) or not isinstance(
                mutation_dispatched, dict
            ):
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle attempt lacks dispatch reconciliation evidence"
                )
            _validate_stored_goal_response(
                stored_precondition.get("goal_get_response"),
                owner=owner,
                expected_state=request.expected_state,
                method="thread/goal/get",
                label="precondition",
            )
            transition_request = _request_frame_from_marker(mutation_dispatched)
            if stored_response is not None and not isinstance(stored_response, dict):
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle attempt mutation response is not an object"
                )
            if isinstance(stored_response, dict):
                stored_goal = runtime._goal_object(
                    stored_response, GOAL_TRANSITION_METHOD
                )
                runtime._validate_goal_binding(stored_goal, owner)
                if runtime._string_at(stored_goal, ("status",)) != request.desired_state:
                    raise runtime.ExternalCodexReturnError(
                        "Goal lifecycle attempt mutation response did not confirm the desired state"
                    )
            transition_proof = _transition_proof(
                owner=owner,
                precondition=stored_precondition,
                mutation_response=stored_response,
                post_read_response=before_response,
                request_frame=transition_request,
                from_state=request.expected_state,
                to_state=request.desired_state,
            )
            attempt["state"] = "proof_recorded"
            attempt["post_read_response"] = before_response
            attempt["transition_request"] = transition_request
            attempt["transition_proof"] = transition_proof
            if attempt_path is None:
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle attempt reservation path is required"
                )
            _write_attempt(
                attempt_path,
                attempt,
                request=request,
                decision=decision,
                owner=owner,
                owner_path=owner_path,
                owner_bytes=owner_bytes,
                endpoint=endpoint,
            )
            mutation_response = stored_response
            authoritative_response = before_response
            resulting_response = authoritative_response
            resulting_state = request.desired_state
            status = "executed"
            method = GOAL_TRANSITION_METHOD
            recovery = {
                "mode": "ambiguous_post_mutation",
                "mutation_response_available": isinstance(stored_response, dict),
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
        elif before_state == request.desired_state:
            if attempt_path is not None:
                content_ref_type, _decision_type, _execution_type, _request_type, _scope, _assert_receipt_scope, canonical_digest = _contract_types()
                attempt = _attempt_binding(
                    request=request,
                    decision=decision,
                    owner=owner,
                    owner_path=owner_path,
                    owner_bytes=owner_bytes,
                    endpoint=endpoint,
                    attempt_path=attempt_path,
                    precondition=precondition,
                    content_ref_type=content_ref_type,
                    canonical_digest=canonical_digest,
                )
                attempt["state"] = "read_only_recorded"
                _write_attempt(
                    attempt_path,
                    attempt,
                    request=request,
                    decision=decision,
                    owner=owner,
                    owner_path=owner_path,
                    owner_bytes=owner_bytes,
                    endpoint=endpoint,
                )
            resulting_response = before_response
            resulting_state = before_state
            status = "replayed"
            method = "thread/goal/get"
            transition_request = None
            transition_proof = None
            recovery = None
        else:
            if attempt is not None:
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle mutation already has a durable attempt; refusing to issue a second lifecycle set"
                )
            if before_state != request.expected_state:
                raise runtime.ExternalCodexReturnError(
                    "Codex app-server Goal state does not match the accepted "
                    "lifecycle precondition"
                )
            if attempt_path is None:
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle mutation requires a durable attempt reservation"
                )
            for path, expected, label in artifact_snapshots:
                runtime.VISIBLE._assert_file_snapshot(path, expected, label)
            content_ref_type, _decision_type, _execution_type, _request_type, _scope, _assert_receipt_scope, canonical_digest = _contract_types()
            attempt = _attempt_binding(
                request=request,
                decision=decision,
                owner=owner,
                owner_path=owner_path,
                owner_bytes=owner_bytes,
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
                owner_bytes=owner_bytes,
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
                    owner_bytes=owner_bytes,
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
                    owner_bytes=owner_bytes,
                )

            previous_prepare_callback = getattr(rpc, "request_prepare_callback", None)
            previous_issued_callback = getattr(rpc, "request_issued_callback", None)
            setattr(rpc, "request_prepare_callback", record_request_prepared)
            setattr(rpc, "request_issued_callback", record_request_issued)
            try:
                for path, expected, label in artifact_snapshots:
                    runtime.VISIBLE._assert_file_snapshot(path, expected, label)
                runtime.VISIBLE._assert_file_snapshot(
                    owner_path, owner_bytes, "Goal lifecycle owner"
                )
                mutation_response = rpc.call(
                    GOAL_TRANSITION_METHOD,
                    {"threadId": owner["thread_id"], "status": request.desired_state},
                )
            finally:
                setattr(rpc, "request_prepare_callback", previous_prepare_callback)
                setattr(rpc, "request_issued_callback", previous_issued_callback)
            if not isinstance(mutation_response, dict):
                raise runtime.ExternalCodexReturnError(
                    "Codex app-server Goal set returned a non-object response"
                )
            mutation_dispatched = attempt.get("mutation_dispatched")
            if not isinstance(mutation_dispatched, dict):
                raise runtime.ExternalCodexReturnError(
                    "Goal lifecycle mutation returned without its durable dispatch marker"
                )
            transition_request = _request_frame_from_marker(mutation_dispatched)
            mutation_goal = runtime._goal_object(
                mutation_response, GOAL_TRANSITION_METHOD
            )
            runtime._validate_goal_binding(mutation_goal, owner)
            if runtime._string_at(mutation_goal, ("status",)) != request.desired_state:
                raise runtime.ExternalCodexReturnError(
                    "Codex app-server Goal set response did not confirm the requested lifecycle state"
                )
            attempt["goal_response"] = mutation_response
            attempt["transition_request"] = transition_request
            _write_attempt(
                attempt_path,
                attempt,
                request=request,
                decision=decision,
                owner=owner,
                owner_path=owner_path,
                owner_bytes=owner_bytes,
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
            transition_proof = _transition_proof(
                owner=owner,
                precondition=precondition,
                mutation_response=mutation_response,
                post_read_response=authoritative_response,
                request_frame=transition_request,
                from_state=request.expected_state,
                to_state=request.desired_state,
            )
            attempt["state"] = "proof_recorded"
            attempt["post_read_response"] = authoritative_response
            attempt["transition_proof"] = transition_proof
            _write_attempt(
                attempt_path,
                attempt,
                request=request,
                decision=decision,
                owner=owner,
                owner_path=owner_path,
                owner_bytes=owner_bytes,
                endpoint=endpoint,
            )
            resulting_response = authoritative_response
            resulting_state = authoritative_state
            status = "executed"
            method = GOAL_TRANSITION_METHOD
            recovery = None
    runtime.VISIBLE._assert_file_snapshot(
        owner_path, owner_bytes, "Goal lifecycle owner"
    )
    receipt = _execution_projection(
        request=request,
        decision=decision,
        owner=owner,
        owner_path=owner_path,
        owner_bytes=owner_bytes,
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
    runtime.VISIBLE._assert_file_snapshot(
        owner_path, owner_bytes, "Goal lifecycle owner"
    )
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
    """Execute one accepted semantic request through the Codex Goal API.

    Every execution must name a durable attempt artifact, including a
    no-mutation read-only completion.
    Serialization combines the qualified Goal identity, semantic idempotency
    key, and physical attempt coordinate so neither competing requests nor
    caller-selected evidence paths can split one mutation attempt.
    """

    if attempt_path is None:
        raise _runtime().ExternalCodexReturnError(
            "Goal lifecycle execution requires a durable attempt path"
        )
    runtime = _runtime()
    attempt_path = runtime._validate_output_path(
        Path(attempt_path), "Goal lifecycle attempt reservation"
    )
    request_type = _contract_types()[3]
    typed_request = _model(request, request_type, "Goal lifecycle request")
    validated_owner = runtime.validate_goal_lifecycle_owner(owner)
    owner_path = runtime._regular_file(Path(owner_path), "Goal lifecycle owner")
    owner_artifact, _owner_bytes = runtime._load_json_file(
        owner_path, "Goal lifecycle owner"
    )
    owner_artifact = runtime.validate_goal_lifecycle_owner(owner_artifact)
    if owner_artifact != validated_owner:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle owner artifact does not match the supplied owner"
        )
    _validate_request_owner_scope(typed_request, validated_owner)
    with _goal_transition_attempt_locks(
        typed_request,
        validated_owner,
        attempt_path,
    ) as attempt_path:
        if attempt is not None:
            _require_supplied_attempt_artifact(attempt_path, attempt)
        resolved_endpoint = _resolve_owner_endpoint(
            validated_owner,
            Path(endpoint),
            rpc_factory=rpc_factory,
        )
        return _execute_goal_transition_unlocked(
            request,
            decision,
            owner,
            owner_path,
            resolved_endpoint,
            rpc_factory=rpc_factory,
            attempt_path=attempt_path,
            attempt=attempt,
            endpoint_is_owner_resolved=True,
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
    if (
        not runtime._is_sha256_digest(before_digest)
        or not runtime._is_sha256_digest(result_digest)
        or (
            mutation_digest is not None
            and not runtime._is_sha256_digest(mutation_digest)
        )
        or not isinstance(request_frame, dict)
    ):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt transition evidence is not bound to its request and response"
        )
    _validated_transition_proof(
        proof,
        owner=owner,
        precondition={"goal_response_sha256": before_digest},
        mutation_response=None,
        expected_mutation_response_digest=mutation_digest,
        post_read_response=result_response,
        request_frame=request_frame,
        from_state=request.expected_state,
        to_state=request.desired_state,
    )
    recovery = lifecycle.get("recovery")
    if recovery is not None and (
        not isinstance(recovery, dict)
        or recovery.get("mode") != "ambiguous_post_mutation"
        or recovery.get("mutation_response_available")
        is not (mutation_digest is not None)
        or recovery.get("reconciled_by") != "thread/goal/get"
        or not isinstance(recovery.get("authoritative"), dict)
        or recovery.get("authoritative")
        != runtime._safe_response_summary(result_response)
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
    if not runtime._is_sha256_digest(result_digest):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt authoritative result evidence is not bound"
        )
    # A receipt's result response is immutable historical evidence.  The
    # current read is a state/identity check only: app-server metadata may
    # legitimately change between a receipt publication and a replay.
    goal = runtime._goal_object(response, "thread/goal/get")
    runtime._validate_goal_binding(goal, owner)
    state = runtime._string_at(goal, ("status",))
    if state != value.get("desired_state"):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt authoritative Goal state no longer matches"
        )


def _validate_receipt_attempt_binding(
    value: dict[str, Any],
    *,
    attempt: dict[str, Any],
    request: Any,
    owner: dict[str, Any],
) -> None:
    """Bind receipt evidence to the durable attempt that authorized it."""

    status = value.get("status")
    if status == "replayed":
        runtime = _runtime()
        if attempt.get("state") != "read_only_recorded":
            raise runtime.ExternalCodexReturnError(
                "existing replayed Goal lifecycle receipt requires a read-only-recorded attempt"
            )
        stored_read = _validated_read_only_precondition(
            attempt.get("precondition"),
            owner=owner,
            desired_state=request.desired_state,
        )
        stored_summary = runtime._safe_response_summary(stored_read)
        stored_digest = runtime._sha256_bytes(runtime._canonical_bytes(stored_read))
        lifecycle = value.get("lifecycle")
        if (
            not isinstance(lifecycle, dict)
            or lifecycle.get("before") != stored_summary
            or lifecycle.get("result") != stored_summary
            or lifecycle.get("result_response") != stored_read
            or lifecycle.get("before_response_sha256") != stored_digest
            or lifecycle.get("result_response_sha256") != stored_digest
            or lifecycle.get("mutation_response_sha256") is not None
            or lifecycle.get("transition_request") is not None
            or lifecycle.get("transition_proof") is not None
        ):
            raise runtime.ExternalCodexReturnError(
                "existing replayed Goal lifecycle receipt read-only evidence does not match its attempt"
            )
        return
    if status != "executed":
        return
    runtime = _runtime()
    if attempt.get("state") != "proof_recorded":
        raise runtime.ExternalCodexReturnError(
            "existing executed Goal lifecycle receipt requires a proof-recorded attempt"
        )
    precondition = attempt.get("precondition")
    mutation_response = attempt.get("goal_response")
    transition_request = attempt.get("transition_request")
    transition_proof = attempt.get("transition_proof")
    stored_post_read_response = attempt.get("post_read_response")
    legacy_transition_proof = (
        isinstance(transition_proof, dict)
        and transition_proof.get("schema_version")
        == LEGACY_GOAL_TRANSITION_PROOF_SCHEMA_VERSION
    )
    if legacy_transition_proof:
        # Legacy atomic receipts had no separately bound post-read.  Ignore
        # any optional later field and project the stored mutation response as
        # the one historical result everywhere in the replay binding.
        post_read_response = mutation_response
    else:
        post_read_response = stored_post_read_response
    if (
        not isinstance(precondition, dict)
        or (
            mutation_response is not None
            and not isinstance(mutation_response, dict)
        )
        or not isinstance(post_read_response, dict)
        or not isinstance(transition_request, dict)
        or not isinstance(transition_proof, dict)
    ):
        raise runtime.ExternalCodexReturnError(
            "existing executed Goal lifecycle attempt lacks complete transition evidence"
        )
    precondition_response = precondition.get("goal_get_response")
    precondition_summary = precondition.get("goal_get")
    precondition_digest = precondition.get("goal_response_sha256")
    if (
        not isinstance(precondition_response, dict)
        or not isinstance(precondition_summary, dict)
        or not runtime._is_sha256_digest(precondition_digest)
        or runtime._sha256_bytes(runtime._canonical_bytes(precondition_response))
        != precondition_digest
        or runtime._safe_response_summary(precondition_response)
        != precondition_summary
        or precondition.get("goal_get_summary_sha256")
        != runtime._sha256_bytes(runtime._canonical_bytes(precondition_summary))
    ):
        raise runtime.ExternalCodexReturnError(
            "existing executed Goal lifecycle attempt precondition evidence is not bound"
        )
    _validate_stored_goal_response(
        precondition_response,
        owner=owner,
        expected_state=request.expected_state,
        method="thread/goal/get",
        label="precondition",
    )
    if isinstance(mutation_response, dict):
        _validate_stored_goal_response(
            mutation_response,
            owner=owner,
            expected_state=request.desired_state,
            method=GOAL_TRANSITION_METHOD,
            label="mutation",
        )
    if not legacy_transition_proof:
        _validate_stored_goal_response(
            post_read_response,
            owner=owner,
            expected_state=request.desired_state,
            method="thread/goal/get",
            label="post-read",
        )
    _validated_transition_proof(
        transition_proof,
        owner=owner,
        precondition=precondition,
        mutation_response=mutation_response,
        post_read_response=post_read_response,
        request_frame=transition_request,
        from_state=request.expected_state,
        to_state=request.desired_state,
    )
    lifecycle = value.get("lifecycle")
    if not isinstance(lifecycle, dict):
        raise runtime.ExternalCodexReturnError(
            "existing executed Goal lifecycle receipt lacks transition evidence"
        )
    if (
        lifecycle.get("before_response_sha256") != precondition_digest
        or lifecycle.get("before") != precondition_summary
        or lifecycle.get("mutation_response_sha256")
        != (
            runtime._sha256_bytes(runtime._canonical_bytes(mutation_response))
            if mutation_response is not None
            else None
        )
        or lifecycle.get("result_response_sha256")
        != runtime._sha256_bytes(runtime._canonical_bytes(post_read_response))
        or lifecycle.get("transition_request") != transition_request
        or lifecycle.get("transition_proof") != transition_proof
    ):
        raise runtime.ExternalCodexReturnError(
            "existing Goal lifecycle receipt transition evidence does not match its attempt"
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
    owner_bytes = owner_path.read_bytes()
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
            owner_bytes=owner_bytes,
            endpoint=Path(value["transport"]["endpoint"]),
            attempt_path=attempt_path,
        )
        _validate_receipt_attempt_binding(
            value,
            attempt=attempt_value,
            request=request,
            owner=owner,
        )
    if (
        value.get("owner_ref") != str(owner_path.resolve())
        or value.get("owner_sha256") != runtime._sha256_bytes(owner_bytes)
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


def _semantic_attempt_lock_path(
    request: Any,
    owner: dict[str, Any],
) -> Path:
    """Derive one lock coordinate from semantic authority, not output names."""

    digest = _semantic_attempt_digest(request, owner)
    return _semantic_attempt_lock_root() / f"{digest}.lock"


def _physical_attempt_lock_path(attempt_path: Path) -> Path:
    """Bind one lock to a lifecycle artifact coordinate, independent of role."""

    runtime = _runtime()
    binding = {
        "schema_version": "abyss_stack_goal_lifecycle_physical_attempt_lock_v1",
        "attempt_ref": str(Path(attempt_path).resolve()),
    }
    digest = runtime._sha256_bytes(runtime._canonical_bytes(binding))
    return _semantic_attempt_lock_root() / f"physical-{digest}.lock"


@contextlib.contextmanager
def _physical_coordinate_locks(paths: tuple[Path, ...]):
    """Acquire a globally ordered lock set for all lifecycle artifact paths."""

    lock_paths = sorted(
        {_physical_attempt_lock_path(path) for path in paths},
        key=lambda path: str(path),
    )
    with contextlib.ExitStack() as stack:
        for lock_path in lock_paths:
            stack.enter_context(_attempt_lock(lock_path))
        yield


def _semantic_attempt_digest(request: Any, owner: dict[str, Any]) -> str:
    """Bind lock and durable attempt selection to one semantic request."""

    runtime = _runtime()
    binding = {
        "schema_version": "abyss_stack_goal_lifecycle_lock_v1",
        "idempotency_key": request.idempotency_key,
        "owner": {
            "owner_id": owner["owner_id"],
            "owner_repo": owner["owner_repo"],
            "goal_id": owner["goal_id"],
            "thread_id": owner["thread_id"],
            "goal_ref": owner["goal_ref"],
            "return_owner_ref": owner["return_owner_ref"],
        },
    }
    return runtime._sha256_bytes(runtime._canonical_bytes(binding))


def _semantic_attempt_anchor_path(request: Any, owner: dict[str, Any]) -> Path:
    digest = _semantic_attempt_digest(request, owner)
    return _semantic_attempt_state_root() / f"{digest}.attempt-anchor.json"


def _resolve_semantic_attempt_path(
    request: Any,
    owner: dict[str, Any],
    requested_path: Path,
) -> Path:
    """Resolve every caller path through one durable semantic anchor."""

    runtime = _runtime()
    requested_path = runtime._validate_output_path(
        Path(requested_path), "Goal lifecycle requested attempt reservation"
    )
    anchor_path = runtime._validate_output_path(
        _semantic_attempt_anchor_path(request, owner),
        "Goal lifecycle semantic attempt anchor",
    )
    digest = _semantic_attempt_digest(request, owner)
    if anchor_path.exists():
        anchor, raw = runtime._load_json_file(
            anchor_path, "Goal lifecycle semantic attempt anchor"
        )
        if raw != runtime._canonical_bytes(anchor) + b"\n":
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle semantic attempt anchor is not canonically encoded"
            )
        legacy_anchor = (
            set(anchor)
            == {
                "schema_version",
                "semantic_attempt_sha256",
                "attempt_ref",
            }
            and anchor.get("schema_version")
            == LEGACY_SEMANTIC_ATTEMPT_ANCHOR_SCHEMA_VERSION
        )
        current_anchor = (
            set(anchor)
            == {
                "schema_version",
                "semantic_attempt_sha256",
                "attempt_ref",
                "attempt_started",
            }
            and anchor.get("schema_version")
            == SEMANTIC_ATTEMPT_ANCHOR_SCHEMA_VERSION
            and isinstance(anchor.get("attempt_started"), bool)
        )
        if (
            not (legacy_anchor or current_anchor)
            or anchor.get("semantic_attempt_sha256") != digest
            or not isinstance(anchor.get("attempt_ref"), str)
        ):
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle semantic attempt anchor binding mismatch"
            )
        anchored_path = Path(anchor["attempt_ref"])
        if not anchored_path.is_absolute() or anchored_path.is_symlink():
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle semantic attempt anchor path binding mismatch"
            )
        if (
            current_anchor
            and not anchor["attempt_started"]
            and not anchored_path.exists()
            and not anchored_path.parent.exists()
        ):
            rebound_anchor = {
                **anchor,
                "attempt_ref": str(requested_path.resolve()),
            }
            runtime._replace_json(
                anchor_path,
                rebound_anchor,
                "Goal lifecycle semantic attempt anchor",
            )
            return requested_path
        anchored_path = runtime._validate_output_path(
            anchored_path,
            "Goal lifecycle anchored attempt reservation",
        )
        if (
            not anchored_path.exists()
            and (legacy_anchor or anchor["attempt_started"])
        ):
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle anchored attempt reservation is missing; refusing to recreate a completed semantic attempt"
            )
        return anchored_path
    anchor = {
        "schema_version": SEMANTIC_ATTEMPT_ANCHOR_SCHEMA_VERSION,
        "semantic_attempt_sha256": digest,
        "attempt_ref": str(requested_path.resolve()),
        "attempt_started": False,
    }
    runtime._write_new_json(
        anchor_path,
        anchor,
        "Goal lifecycle semantic attempt anchor",
    )
    return requested_path


def _mark_semantic_attempt_started(
    request: Any,
    owner: dict[str, Any],
    attempt_path: Path,
) -> None:
    """Promote an anchor only after its bound attempt exists and validates."""

    runtime = _runtime()
    anchor_path = runtime._validate_output_path(
        _semantic_attempt_anchor_path(request, owner),
        "Goal lifecycle semantic attempt anchor",
    )
    anchor, raw = runtime._load_json_file(
        runtime._regular_file(anchor_path, "Goal lifecycle semantic attempt anchor"),
        "Goal lifecycle semantic attempt anchor",
    )
    if raw != runtime._canonical_bytes(anchor) + b"\n":
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle semantic attempt anchor is not canonically encoded"
        )
    digest = _semantic_attempt_digest(request, owner)
    expected_ref = str(Path(attempt_path).resolve())
    legacy_anchor = (
        set(anchor)
        == {
            "schema_version",
            "semantic_attempt_sha256",
            "attempt_ref",
        }
        and anchor.get("schema_version")
        == LEGACY_SEMANTIC_ATTEMPT_ANCHOR_SCHEMA_VERSION
    )
    current_anchor = (
        set(anchor)
        == {
            "schema_version",
            "semantic_attempt_sha256",
            "attempt_ref",
            "attempt_started",
        }
        and anchor.get("schema_version")
        == SEMANTIC_ATTEMPT_ANCHOR_SCHEMA_VERSION
        and isinstance(anchor.get("attempt_started"), bool)
    )
    if (
        not (legacy_anchor or current_anchor)
        or anchor.get("semantic_attempt_sha256") != digest
        or anchor.get("attempt_ref") != expected_ref
    ):
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle semantic attempt anchor binding mismatch"
        )
    if current_anchor and anchor["attempt_started"]:
        return
    runtime._replace_json(
        anchor_path,
        {
            "schema_version": SEMANTIC_ATTEMPT_ANCHOR_SCHEMA_VERSION,
            "semantic_attempt_sha256": digest,
            "attempt_ref": expected_ref,
            "attempt_started": True,
        },
        "Goal lifecycle semantic attempt anchor",
    )


def _semantic_attempt_lock_root() -> Path:
    """Return one owner-private host coordinate across endpoint rebinding."""

    runtime = _runtime()
    uid = os.getuid()
    runtime_parent = Path(f"/run/user/{uid}")
    if runtime_parent.is_symlink() or not runtime_parent.is_dir():
        runtime_parent = Path("/tmp")
    if runtime_parent.is_symlink() or not runtime_parent.is_dir():
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle semantic lock parent is not a real directory"
        )
    root = runtime_parent / f"aoa-external-codex-goal-lifecycle-{uid}"
    try:
        root.mkdir(mode=0o700, exist_ok=True)
        observed = root.stat(follow_symlinks=False)
    except OSError as exc:
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle semantic lock root cannot be prepared: {root}"
        ) from exc
    if (
        root.is_symlink()
        or not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != uid
        or stat.S_IMODE(observed.st_mode) & 0o077
    ):
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle semantic lock root is not owner-private: {root}"
        )
    return root


def _semantic_attempt_state_root() -> Path:
    """Return persistent owner state for semantic idempotency anchors."""

    runtime = _runtime()
    uid = os.getuid()
    try:
        home = Path(pwd.getpwuid(uid).pw_dir).resolve(strict=True)
        home_stat = home.stat(follow_symlinks=False)
    except (KeyError, OSError) as exc:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle semantic state home cannot be resolved"
        ) from exc
    if (
        not stat.S_ISDIR(home_stat.st_mode)
        or home_stat.st_uid != uid
        or stat.S_IMODE(home_stat.st_mode) & 0o022
    ):
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle semantic state home is not owner-controlled: {home}"
        )
    local_parent = home / ".local"
    state_parent = local_parent / "state"
    owner_parent = state_parent / "aoa-external-codex"
    root = owner_parent / "goal-lifecycle"
    for directory, forbidden_mode in (
        (local_parent, 0o022),
        (state_parent, 0o022),
        (owner_parent, 0o022),
        (root, 0o077),
    ):
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
            observed = directory.stat(follow_symlinks=False)
        except OSError as exc:
            raise runtime.ExternalCodexReturnError(
                f"Goal lifecycle semantic state directory cannot be prepared: {directory}"
            ) from exc
        if (
            directory.is_symlink()
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != uid
            or stat.S_IMODE(observed.st_mode) & forbidden_mode
        ):
            raise runtime.ExternalCodexReturnError(
                f"Goal lifecycle semantic state directory is not owner-controlled: {directory}"
            )
    return root


@contextlib.contextmanager
def _attempt_lock(path: Path):
    runtime = _runtime()
    lock_path = runtime._validate_output_path(
        path, "Goal lifecycle semantic attempt lock"
    )
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise runtime.ExternalCodexReturnError(
            f"cannot open Goal lifecycle semantic attempt lock: {lock_path}"
        ) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise runtime.ExternalCodexReturnError(
            f"Goal lifecycle semantic attempt lock failed: {lock_path}"
        ) from exc
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextlib.contextmanager
def _goal_transition_attempt_locks(
    request: Any,
    owner: dict[str, Any],
    requested_attempt_path: Path,
    *,
    additional_physical_paths: tuple[Path, ...] = (),
):
    """Serialize one transition by Goal, semantic request, and artifact paths."""

    runtime = _runtime()
    semantic_lock_path = _semantic_attempt_lock_path(request, owner)
    # Reuse the legacy pause lock as the common native Goal mutation boundary.
    # Goal identity is always outermost so every lifecycle route has one lock
    # order and cannot deadlock while acquiring narrower request/path locks.
    with runtime._pause_attempt_lock(owner):
        with _attempt_lock(semantic_lock_path):
            attempt_path = _resolve_semantic_attempt_path(
                request,
                owner,
                requested_attempt_path,
            )
            with _physical_coordinate_locks(
                (attempt_path, *additional_physical_paths)
            ):
                yield attempt_path


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
    _load_schema(owner, _goal_owner_schema_path(), "Goal lifecycle owner")
    _validate_request_owner_scope(request, owner)
    input_paths = {
        request_path.resolve(),
        decision_path.resolve(),
        owner_path.resolve(),
    }
    if {receipt_path.resolve(), attempt_path.resolve()} & input_paths:
        raise runtime.ExternalCodexReturnError(
            "Goal lifecycle receipt must be distinct from all input artifacts"
        )
    with _goal_transition_attempt_locks(
        request,
        owner,
        attempt_path,
        additional_physical_paths=(receipt_path,),
    ) as attempt_path:
        if {receipt_path.resolve(), attempt_path.resolve()} & input_paths:
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle receipt and anchored attempt must be distinct from all input artifacts"
            )
        if receipt_path.resolve() == attempt_path.resolve():
            raise runtime.ExternalCodexReturnError(
                "Goal lifecycle receipt must be distinct from its anchored attempt"
            )
        endpoint, resolution = runtime.discover_app_server_socket(owner)
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
        receipt = _execute_goal_transition_unlocked(
            request,
            decision,
            owner,
            owner_path,
            endpoint,
            attempt_path=attempt_path,
            attempt=attempt,
            endpoint_is_owner_resolved=True,
            artifact_snapshots=(
                (request_path, request_bytes, "Goal lifecycle request"),
                (decision_path, decision_bytes, "Goal lifecycle decision"),
            ),
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
        for path, expected, label in (
            (request_path, request_bytes, "Goal lifecycle request"),
            (decision_path, decision_bytes, "Goal lifecycle decision"),
            (owner_path, owner_bytes, "Goal lifecycle owner"),
        ):
            runtime.VISIBLE._assert_file_snapshot(path, expected, label)
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
