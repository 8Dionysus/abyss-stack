"""Runtime boundary for provider-neutral programmatic tool execution.

The SDK owns the request and observation ABI.  This module owns only the
runtime adapter seam, the explicit disabled-by-default gate, and validation of
the observation returned by a selected adapter.  It does not launch a host,
select a model, enforce a sandbox, or assign an eval verdict.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Protocol, runtime_checkable

from aoa_sdk.contracts.control_plane import ContentRef
from aoa_sdk.contracts.programmatic_execution import (
    ProgrammaticExecutionObservation,
    ProgrammaticExecutionRequest,
    assert_programmatic_execution_admitted,
    assert_programmatic_execution_observation,
)


CODEX_CODE_MODE_HOST_ADAPTER_ID = "codex-code-mode-host"
LOCAL_MODEL_SUBSTRATE_ADAPTER_ID = "local-model-substrate"

AdapterInvoker = Callable[
    [ProgrammaticExecutionRequest], ProgrammaticExecutionObservation
]


class _UnsetExecutionCompletion:
    """Sentinel distinguishing omitted completion from an explicit unknown."""


_UNSET_EXECUTION_COMPLETION = _UnsetExecutionCompletion()


class ProgrammaticExecutionRuntimeError(RuntimeError):
    """A stable, fail-closed runtime boundary error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        observation: ProgrammaticExecutionObservation | None = None,
        execution_completed: bool | None | _UnsetExecutionCompletion = _UNSET_EXECUTION_COMPLETION,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.observation = observation
        if isinstance(execution_completed, _UnsetExecutionCompletion):
            self.execution_completed: bool | None = observation is not None
        else:
            self.execution_completed = execution_completed


class ProgrammaticAdapterError(ProgrammaticExecutionRuntimeError):
    """An adapter cannot satisfy the selected execution request."""


class _AdapterPreInvocationError(ProgrammaticAdapterError):
    """An adapter rejected the request before its bound invoker ran."""


@runtime_checkable
class ProgrammaticExecutionAdapter(Protocol):
    """Runtime-owned adapter ABI for one provider-neutral execution."""

    @property
    def adapter_id(self) -> str: ...

    def execute(
        self, request: ProgrammaticExecutionRequest
    ) -> ProgrammaticExecutionObservation: ...


def _invoke(
    *,
    adapter_id: str,
    invoker: AdapterInvoker | None,
    request: ProgrammaticExecutionRequest,
) -> ProgrammaticExecutionObservation:
    if request.adapter_id != adapter_id:
        raise _AdapterPreInvocationError(
            "adapter_identity_mismatch",
            f"request selects {request.adapter_id!r}, not {adapter_id!r}",
        )
    if invoker is None:
        raise _AdapterPreInvocationError(
            f"{adapter_id}_unbound",
            f"{adapter_id} has no bound runtime invoker",
        )
    return invoker(request)


@dataclass(frozen=True)
class CodexCodeModeHostAdapter:
    """First adapter seam for an explicitly bound Codex code-mode host."""

    host_ref: ContentRef
    invoker: AdapterInvoker | None = None
    ADAPTER_ID: ClassVar[str] = CODEX_CODE_MODE_HOST_ADAPTER_ID

    @property
    def adapter_id(self) -> str:
        return self.ADAPTER_ID

    def execute(
        self, request: ProgrammaticExecutionRequest
    ) -> ProgrammaticExecutionObservation:
        return _invoke(
            adapter_id=self.adapter_id,
            invoker=self.invoker,
            request=request,
        )


@dataclass(frozen=True)
class LocalModelSubstrateAdapter:
    """Independent adapter seam for an existing local-model substrate route."""

    route_ref: ContentRef
    invoker: AdapterInvoker | None = None
    ADAPTER_ID: ClassVar[str] = LOCAL_MODEL_SUBSTRATE_ADAPTER_ID

    @property
    def adapter_id(self) -> str:
        return self.ADAPTER_ID

    def execute(
        self, request: ProgrammaticExecutionRequest
    ) -> ProgrammaticExecutionObservation:
        return _invoke(
            adapter_id=self.adapter_id,
            invoker=self.invoker,
            request=request,
        )


@dataclass(frozen=True)
class ProgrammaticExecutionRuntime:
    """Dispatch admitted requests and retain validated runtime observations."""

    adapters: Mapping[str, ProgrammaticExecutionAdapter]
    enabled: bool = False
    observation_sink: Callable[[ProgrammaticExecutionObservation], None] | None = None

    def __post_init__(self) -> None:
        adapters = dict(self.adapters)
        if not adapters:
            raise ProgrammaticExecutionRuntimeError(
                "no_adapters", "programmatic execution requires an adapter"
            )
        for key, adapter in adapters.items():
            if not isinstance(key, str) or not key:
                raise ProgrammaticExecutionRuntimeError(
                    "invalid_adapter_key", "adapter registry keys must be non-empty strings"
                )
            if not isinstance(adapter, ProgrammaticExecutionAdapter):
                raise ProgrammaticExecutionRuntimeError(
                    "invalid_adapter", f"adapter {key!r} does not implement the runtime ABI"
                )
            if adapter.adapter_id != key:
                raise ProgrammaticExecutionRuntimeError(
                    "adapter_registry_mismatch",
                    f"adapter registry key {key!r} does not match {adapter.adapter_id!r}",
                )
        object.__setattr__(self, "adapters", MappingProxyType(adapters))

    def execute(
        self, request: ProgrammaticExecutionRequest
    ) -> ProgrammaticExecutionObservation:
        """Run one request only after explicit admission and runtime enablement."""

        assert_programmatic_execution_admitted(request)
        if not self.enabled:
            raise ProgrammaticExecutionRuntimeError(
                "programmatic_execution_disabled",
                "programmatic execution runtime is disabled by default",
            )
        adapter = self.adapters.get(request.adapter_id)
        if adapter is None:
            raise ProgrammaticExecutionRuntimeError(
                "adapter_not_registered",
                f"no runtime adapter is registered for {request.adapter_id!r}",
            )
        try:
            observation = adapter.execute(request)
        except _AdapterPreInvocationError:
            raise
        except Exception as exc:
            raise ProgrammaticAdapterError(
                "adapter_execution_failed",
                "the selected adapter failed without returning an observation; "
                "execution completion is unknown",
                execution_completed=None,
            ) from exc
        try:
            assert_programmatic_execution_observation(request, observation)
        except Exception as exc:
            returned_completion: bool | None = (
                True if observation is not None else None
            )
            retained_observation = (
                observation
                if isinstance(observation, ProgrammaticExecutionObservation)
                else None
            )
            raise ProgrammaticExecutionRuntimeError(
                "invalid_observation",
                f"adapter returned an invalid programmatic execution observation: {exc}",
                observation=retained_observation,
                execution_completed=returned_completion,
            ) from exc
        if self.observation_sink is not None:
            try:
                self.observation_sink(observation)
            except Exception as exc:
                raise ProgrammaticExecutionRuntimeError(
                    "observation_sink_failed",
                    "validated execution completed but recording its observation failed; "
                    "preserve the attached observation before considering a retry",
                    observation=observation,
                ) from exc
        return observation
