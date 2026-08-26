from __future__ import annotations

import hashlib
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest
from aoa_sdk.contracts.control_plane import (
    ContentRef,
    ControlPlaneContractError,
    ProvenanceRef,
)
from aoa_sdk.contracts.programmatic_execution import (
    PROGRAMMATIC_ADMISSION_SCHEMA_VERSION,
    ProgrammaticActivation,
    ProgrammaticActivationRequirements,
    ProgrammaticEconomyObservation,
    ProgrammaticEffectCeiling,
    ProgrammaticExecutionObservation,
    ProgrammaticExecutionRequest,
    ProgrammaticObservationDimension,
    ProgrammaticObservationRequirements,
    ProgrammaticToolCallObservation,
    ProgrammaticToolHandle,
    programmatic_execution_request_ref,
)


PART_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PART_ROOT / "programmatic_tool_execution.py"
NOW = datetime(2026, 8, 26, 15, 45, tzinfo=timezone.utc)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "programmatic_tool_execution_under_test", MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load runtime module: {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNTIME = _load_module()


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _ref(object_id: str) -> ContentRef:
    return ContentRef(
        object_id=object_id,
        owner_repo="fixture-owner",
        schema_version="fixture_v1",
        digest=_digest(object_id),
    )


def _provenance(artifact: str) -> ProvenanceRef:
    return ProvenanceRef(
        owner_repo="fixture-owner",
        artifact_ref=artifact,
        source_ref="fixture-source",
        artifact_digest=_digest(artifact),
        schema_ref="fixture.schema.json",
        schema_version="fixture_v1",
    )


def _request(adapter_id: str, *, admitted: bool = True) -> ProgrammaticExecutionRequest:
    plan_ref = _ref("plan")
    profile_ref = _ref("runtime-profile")
    return ProgrammaticExecutionRequest(
        execution_id=f"execution:{adapter_id}",
        correlation_id=f"correlation:{adapter_id}",
        adapter_id=adapter_id,
        mode="programmatic",
        plan_ref=plan_ref,
        runtime_profile_ref=profile_ref,
        input_ref=_ref("input"),
        program_ref=_ref("program"),
        tool_handles=(
            ProgrammaticToolHandle(
                handle_id="tool-handle:read",
                tool_id="read_file",
                input_schema_ref=_ref("schema:input"),
                output_schema_ref=_ref("schema:output"),
                effect_class="read_only",
                provenance=_provenance("tool.json"),
            ),
        ),
        effect_ceiling=ProgrammaticEffectCeiling(sandbox_id="sandbox:fixture"),
        activation_requirements=ProgrammaticActivationRequirements(
            required_plan_ref=plan_ref,
            required_runtime_profile_ref=profile_ref,
        ),
            activation=(
                ProgrammaticActivation(
                    state="admitted",
                    admission_ref=ContentRef(
                        object_id="admission",
                        owner_repo="fixture-owner",
                        schema_version=PROGRAMMATIC_ADMISSION_SCHEMA_VERSION,
                        digest=_digest("admission"),
                    ),
                    admission_authority=ProvenanceRef(
                        owner_repo="fixture-owner",
                        artifact_ref="admission.json",
                        source_ref="fixture-admission-source",
                        artifact_digest=_digest("admission"),
                        schema_ref="admission.schema.json",
                        schema_version=PROGRAMMATIC_ADMISSION_SCHEMA_VERSION,
                    ),
                    plan_ref=plan_ref,
                    runtime_profile_ref=profile_ref,
                    admitted_at=NOW,
                )
            if admitted
            else ProgrammaticActivation()
        ),
        observation_requirements=ProgrammaticObservationRequirements(),
        requested_at=NOW,
        provenance=_provenance("request.json"),
    )


def _observation(request: ProgrammaticExecutionRequest) -> ProgrammaticExecutionObservation:
    call = ProgrammaticToolCallObservation(
        call_id="call:read",
        sequence=1,
        tool_handle_id="tool-handle:read",
        status="succeeded",
        input_ref=_ref("call-input"),
        output_ref=_ref("call-output"),
        intermediate_value_refs=(_ref("intermediate:read"),),
        started_at=NOW,
        finished_at=NOW + timedelta(milliseconds=5),
        wall_time_ms=5,
    )
    dimensions = tuple(
        ProgrammaticObservationDimension(
            dimension=dimension,
            availability="observed",
            evidence_ref=_ref(f"evidence:{dimension}"),
        )
        for dimension in (
            "execution",
            "tool_calls",
            "intermediate_values",
            "failures",
            "economy",
            "wall_time",
            "rework",
        )
    )
    return ProgrammaticExecutionObservation(
        request_ref=programmatic_execution_request_ref(request),
        execution_id=request.execution_id,
        correlation_id=request.correlation_id,
        adapter_id=request.adapter_id,
        status="succeeded",
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=1),
        result_ref=_ref("result"),
        tool_calls=(call,),
        intermediate_value_refs=(_ref("intermediate:read"),),
        economy=ProgrammaticEconomyObservation(
            availability="observed",
            measurement_source="runtime",
            input_tokens=10,
            cached_input_tokens=2,
            output_tokens=4,
            model_calls=1,
            turns=1,
            tool_calls=1,
            intermediate_values=1,
            wall_time_ms=5,
            rework_count=0,
            observed_at=NOW + timedelta(seconds=1),
        ),
        dimension_observations=dimensions,
        provenance=_provenance("observation.json"),
    )


def test_runtime_is_disabled_by_default_before_adapter_invocation() -> None:
    calls: list[str] = []
    adapter = RUNTIME.LocalModelSubstrateAdapter(
        route_ref=_ref("local-route"),
        invoker=lambda request: calls.append(request.execution_id) or _observation(request),
    )
    runtime = RUNTIME.ProgrammaticExecutionRuntime({adapter.adapter_id: adapter})

    with pytest.raises(RUNTIME.ProgrammaticExecutionRuntimeError) as raised:
        runtime.execute(_request(adapter.adapter_id))

    assert raised.value.code == "programmatic_execution_disabled"
    assert calls == []


def test_unadmitted_request_fails_before_disabled_runtime_gate() -> None:
    adapter = RUNTIME.LocalModelSubstrateAdapter(route_ref=_ref("local-route"))
    runtime = RUNTIME.ProgrammaticExecutionRuntime({adapter.adapter_id: adapter})

    with pytest.raises(ControlPlaneContractError, match="not admitted"):
        runtime.execute(_request(adapter.adapter_id, admitted=False))


def test_codex_and_local_adapters_dispatch_independently_and_sink_validated_records() -> None:
    recorded: list[ProgrammaticExecutionObservation] = []
    codex = RUNTIME.CodexCodeModeHostAdapter(
        host_ref=_ref("codex-host"), invoker=_observation
    )
    local = RUNTIME.LocalModelSubstrateAdapter(
        route_ref=_ref("local-route"), invoker=_observation
    )
    runtime = RUNTIME.ProgrammaticExecutionRuntime(
        {codex.adapter_id: codex, local.adapter_id: local},
        enabled=True,
        observation_sink=recorded.append,
    )

    results = [runtime.execute(_request(adapter.adapter_id)) for adapter in (codex, local)]

    assert [result.adapter_id for result in results] == [
        "codex-code-mode-host",
        "local-model-substrate",
    ]
    assert recorded == results


@pytest.mark.parametrize(
    ("adapter_factory", "error_code"),
    [
        (lambda: RUNTIME.CodexCodeModeHostAdapter(host_ref=_ref("codex-host")), "codex-code-mode-host_unbound"),
        (lambda: RUNTIME.LocalModelSubstrateAdapter(route_ref=_ref("local-route")), "local-model-substrate_unbound"),
    ],
)
def test_unbound_adapters_fail_closed(adapter_factory, error_code: str) -> None:
    adapter = adapter_factory()
    runtime = RUNTIME.ProgrammaticExecutionRuntime(
        {adapter.adapter_id: adapter}, enabled=True
    )

    with pytest.raises(RUNTIME.ProgrammaticAdapterError) as raised:
        runtime.execute(_request(adapter.adapter_id))

    assert raised.value.code == error_code


def test_adapter_execution_failure_is_distinct_from_invalid_observation() -> None:
    def failing_invoker(request: ProgrammaticExecutionRequest) -> ProgrammaticExecutionObservation:
        raise TimeoutError(f"timed out: {request.execution_id}")

    adapter = RUNTIME.LocalModelSubstrateAdapter(
        route_ref=_ref("local-route"), invoker=failing_invoker
    )
    runtime = RUNTIME.ProgrammaticExecutionRuntime(
        {adapter.adapter_id: adapter}, enabled=True
    )

    with pytest.raises(RUNTIME.ProgrammaticAdapterError) as raised:
        runtime.execute(_request(adapter.adapter_id))

    assert raised.value.code == "adapter_execution_failed"
    assert raised.value.observation is None
    assert raised.value.execution_completed is False


def test_bound_invoker_runtime_error_is_normalized_as_adapter_failure() -> None:
    def failing_invoker(request: ProgrammaticExecutionRequest) -> ProgrammaticExecutionObservation:
        raise RUNTIME.ProgrammaticExecutionRuntimeError(
            "provider_specific_failure", f"provider failed: {request.execution_id}"
        )

    adapter = RUNTIME.LocalModelSubstrateAdapter(
        route_ref=_ref("local-route"), invoker=failing_invoker
    )
    runtime = RUNTIME.ProgrammaticExecutionRuntime(
        {adapter.adapter_id: adapter}, enabled=True
    )

    with pytest.raises(RUNTIME.ProgrammaticAdapterError) as raised:
        runtime.execute(_request(adapter.adapter_id))

    assert raised.value.code == "adapter_execution_failed"
    assert raised.value.observation is None
    assert raised.value.execution_completed is False


def test_custom_adapter_runtime_error_is_normalized_as_adapter_failure() -> None:
    class FailingAdapter:
        @property
        def adapter_id(self) -> str:
            return "custom-adapter"

        def execute(
            self, request: ProgrammaticExecutionRequest
        ) -> ProgrammaticExecutionObservation:
            raise RUNTIME.ProgrammaticExecutionRuntimeError(
                "provider_specific_failure", f"provider failed: {request.execution_id}"
            )

    adapter = FailingAdapter()
    runtime = RUNTIME.ProgrammaticExecutionRuntime(
        {adapter.adapter_id: adapter}, enabled=True
    )

    with pytest.raises(RUNTIME.ProgrammaticAdapterError) as raised:
        runtime.execute(_request(adapter.adapter_id))

    assert raised.value.code == "adapter_execution_failed"
    assert raised.value.observation is None
    assert raised.value.execution_completed is False


def test_invalid_observation_is_not_sent_to_sink() -> None:
    recorded: list[ProgrammaticExecutionObservation] = []

    def invalid_observation(request: ProgrammaticExecutionRequest) -> ProgrammaticExecutionObservation:
        return _observation(request).model_copy(update={"adapter_id": "wrong-adapter"})

    adapter = RUNTIME.LocalModelSubstrateAdapter(
        route_ref=_ref("local-route"), invoker=invalid_observation
    )
    runtime = RUNTIME.ProgrammaticExecutionRuntime(
        {adapter.adapter_id: adapter}, enabled=True, observation_sink=recorded.append
    )

    with pytest.raises(RUNTIME.ProgrammaticExecutionRuntimeError) as raised:
        runtime.execute(_request(adapter.adapter_id))

    assert raised.value.code == "invalid_observation"
    assert raised.value.observation is not None
    assert raised.value.observation.adapter_id == "wrong-adapter"
    assert raised.value.execution_completed is True
    assert recorded == []


def test_missing_observation_is_indeterminate_and_not_sent_to_sink() -> None:
    recorded: list[ProgrammaticExecutionObservation] = []

    def no_observation(
        request: ProgrammaticExecutionRequest,
    ) -> ProgrammaticExecutionObservation:
        del request
        return None  # type: ignore[return-value]

    adapter = RUNTIME.LocalModelSubstrateAdapter(
        route_ref=_ref("local-route"), invoker=no_observation
    )
    runtime = RUNTIME.ProgrammaticExecutionRuntime(
        {adapter.adapter_id: adapter}, enabled=True, observation_sink=recorded.append
    )

    with pytest.raises(RUNTIME.ProgrammaticExecutionRuntimeError) as raised:
        runtime.execute(_request(adapter.adapter_id))

    assert raised.value.code == "invalid_observation"
    assert raised.value.observation is None
    assert raised.value.execution_completed is None
    assert recorded == []


def test_sink_failure_is_a_post_execution_error_with_the_validated_observation() -> None:
    observed: list[ProgrammaticExecutionObservation] = []

    def sink_failure(observation: ProgrammaticExecutionObservation) -> None:
        observed.append(observation)
        raise OSError("evidence store unavailable")

    adapter = RUNTIME.LocalModelSubstrateAdapter(
        route_ref=_ref("local-route"), invoker=_observation
    )
    runtime = RUNTIME.ProgrammaticExecutionRuntime(
        {adapter.adapter_id: adapter},
        enabled=True,
        observation_sink=sink_failure,
    )

    with pytest.raises(RUNTIME.ProgrammaticExecutionRuntimeError) as raised:
        runtime.execute(_request(adapter.adapter_id))

    assert raised.value.code == "observation_sink_failed"
    assert raised.value.observation is observed[0]
    assert raised.value.execution_completed is True
