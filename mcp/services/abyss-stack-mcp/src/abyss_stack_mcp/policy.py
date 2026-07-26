"""Protocol-independent policy seam for stack MCP tool dispatch."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Literal

from .core import (
    StackMCPError,
    _reject_secret_material,
    canonical_json_bytes,
    sha256_digest,
)


Decision = Literal["allowed", "denied", "cancelled"]


@dataclass(frozen=True)
class PolicyIdentity:
    identity_id: str
    auth_mode: Literal["bearer", "os_process"]
    scope: str


@dataclass(frozen=True)
class ToolPolicy:
    tool_id: str
    effect_class: Literal["observe", "prepare_candidate"]
    max_input_bytes: int
    max_output_bytes: int
    timeout_seconds: float
    filesystem_access: Literal["configured_observation_read"]
    network_access: Literal["none"]
    source_to_sink: Literal[
        "runtime_observation_to_typed_result",
        "runtime_observation_to_nonexecuting_candidate",
    ]


class PolicyDeniedError(StackMCPError):
    """Expose one public-safe denial receipt without echoing request values."""

    def __init__(self, reason_code: str, receipt: dict[str, Any]) -> None:
        self.reason_code = reason_code
        self.receipt = receipt
        rendered = json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        super().__init__(f"policy denied: {reason_code}; receipt={rendered}")


class StackPolicySeam:
    """Apply one bounded policy contour before and after tool dispatch."""

    def __init__(
        self,
        *,
        owner: str,
        policy_family: Literal["read", "candidate"],
        expected_scope: str,
        tools: tuple[ToolPolicy, ...],
        max_in_flight: int,
        rate_limit: int,
        rate_window_seconds: float,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        if max_in_flight < 1:
            raise ValueError("max_in_flight must be positive")
        if rate_limit < 1 or rate_window_seconds <= 0:
            raise ValueError("rate limit and window must be positive")
        tool_map = {tool.tool_id: tool for tool in tools}
        if len(tool_map) != len(tools):
            raise ValueError("tool policy ids must be unique")
        self.owner = owner
        self.policy_family = policy_family
        self.expected_scope = expected_scope
        self._tools = tool_map
        self._max_in_flight = max_in_flight
        self._rate_limit = rate_limit
        self._rate_window_seconds = rate_window_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic_clock or monotonic
        self._state_lock = asyncio.Lock()
        self._in_flight = 0
        self._recent_starts: deque[float] = deque()
        self._audit: deque[dict[str, Any]] = deque(maxlen=256)

    def recent_receipts(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(receipt) for receipt in self._audit)

    def _base_receipt(
        self,
        *,
        request_id: str,
        identity: PolicyIdentity,
        tool: ToolPolicy | None,
        tool_id: str,
        input_digest: str,
        decision: Decision,
        reason_codes: tuple[str, ...],
        output_digest: str | None = None,
    ) -> dict[str, Any]:
        observed_at = self._clock().astimezone(timezone.utc)
        payload = {
            "schema_version": "abyss_stack_mcp_policy_receipt_v1",
            "request_id": request_id,
            "owner": self.owner,
            "identity_id": identity.identity_id,
            "auth_mode": identity.auth_mode,
            "scope": identity.scope,
            "policy_family": self.policy_family,
            "tool_id": tool_id,
            "effect_class": tool.effect_class if tool is not None else "unknown",
            "decision": decision,
            "reason_codes": list(reason_codes),
            "input_digest": input_digest,
            "output_digest": output_digest,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "filesystem_access": (
                tool.filesystem_access if tool is not None else "none"
            ),
            "network_access": (
                tool.network_access if tool is not None else "none"
            ),
            "source_to_sink": (
                tool.source_to_sink if tool is not None else "none"
            ),
            "runtime_effect_authorized": False,
            "approval_state": (
                "required_before_runtime_effect"
                if tool is not None
                and tool.effect_class == "prepare_candidate"
                else "not_applicable"
            ),
            "content_trust": "untrusted_data",
            "instruction_authority": "none",
            "contains_secrets": False,
        }
        return {
            **payload,
            "receipt_id": sha256_digest(payload),
        }

    def _record(self, receipt: dict[str, Any]) -> None:
        self._audit.append(dict(receipt))

    def _release_background_worker(self, task: asyncio.Task[Any]) -> None:
        self._in_flight -= 1
        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    def _deny(
        self,
        *,
        reason_code: str,
        request_id: str,
        identity: PolicyIdentity,
        tool: ToolPolicy | None,
        tool_id: str,
        input_digest: str,
    ) -> PolicyDeniedError:
        receipt = self._base_receipt(
            request_id=request_id,
            identity=identity,
            tool=tool,
            tool_id=tool_id,
            input_digest=input_digest,
            decision="denied",
            reason_codes=(reason_code,),
        )
        self._record(receipt)
        return PolicyDeniedError(reason_code, receipt)

    async def invoke(
        self,
        *,
        request_id: str,
        identity: PolicyIdentity,
        tool_id: str,
        arguments: dict[str, Any],
        dispatch: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        input_bytes = canonical_json_bytes(arguments)
        input_digest = sha256_digest(arguments)
        tool = self._tools.get(tool_id)
        if tool is None:
            raise self._deny(
                reason_code="tool_not_allowlisted",
                request_id=request_id,
                identity=identity,
                tool=None,
                tool_id=tool_id,
                input_digest=input_digest,
            )
        if identity.scope != self.expected_scope:
            raise self._deny(
                reason_code="identity_scope_mismatch",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            )
        if len(input_bytes) > tool.max_input_bytes:
            raise self._deny(
                reason_code="input_size_limit_exceeded",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            )
        try:
            _reject_secret_material(arguments)
        except StackMCPError:
            raise self._deny(
                reason_code="secret_material_rejected",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            ) from None

        now = self._monotonic()
        async with self._state_lock:
            cutoff = now - self._rate_window_seconds
            while self._recent_starts and self._recent_starts[0] <= cutoff:
                self._recent_starts.popleft()
            if len(self._recent_starts) >= self._rate_limit:
                raise self._deny(
                    reason_code="rate_limit_exceeded",
                    request_id=request_id,
                    identity=identity,
                    tool=tool,
                    tool_id=tool_id,
                    input_digest=input_digest,
                )
            if self._in_flight >= self._max_in_flight:
                raise self._deny(
                    reason_code="concurrency_limit_exceeded",
                    request_id=request_id,
                    identity=identity,
                    tool=tool,
                    tool_id=tool_id,
                    input_digest=input_digest,
                )
            self._recent_starts.append(now)
            self._in_flight += 1

        background_release = False
        worker = asyncio.create_task(asyncio.to_thread(dispatch))
        try:
            result = await asyncio.wait_for(
                asyncio.shield(worker),
                timeout=tool.timeout_seconds,
            )
        except TimeoutError:
            background_release = True
            worker.add_done_callback(self._release_background_worker)
            raise self._deny(
                reason_code="dispatch_timeout",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            ) from None
        except StackMCPError:
            raise self._deny(
                reason_code="application_precondition_denied",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            ) from None
        except Exception:
            raise self._deny(
                reason_code="application_failure",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            ) from None
        except asyncio.CancelledError:
            background_release = True
            worker.add_done_callback(self._release_background_worker)
            receipt = self._base_receipt(
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
                decision="cancelled",
                reason_codes=("caller_cancelled",),
            )
            self._record(receipt)
            raise
        finally:
            if not background_release:
                async with self._state_lock:
                    self._in_flight -= 1

        if not isinstance(result, dict):
            raise self._deny(
                reason_code="result_contract_invalid",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            )
        try:
            _reject_secret_material(result)
        except StackMCPError:
            raise self._deny(
                reason_code="secret_result_rejected",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            ) from None
        result_bytes = canonical_json_bytes(result)
        if len(result_bytes) > tool.max_output_bytes:
            raise self._deny(
                reason_code="output_size_limit_exceeded",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            )

        receipt = self._base_receipt(
            request_id=request_id,
            identity=identity,
            tool=tool,
            tool_id=tool_id,
            input_digest=input_digest,
            output_digest=sha256_digest(result),
            decision="allowed",
            reason_codes=(),
        )
        enriched = dict(result)
        metadata = dict(enriched.get("metadata", {}))
        metadata.update(
            {
                "policy_receipt": receipt,
                "content_trust": "untrusted_data",
                "instruction_authority": "none",
            }
        )
        enriched["metadata"] = metadata
        if len(canonical_json_bytes(enriched)) > tool.max_output_bytes:
            raise self._deny(
                reason_code="output_size_limit_exceeded",
                request_id=request_id,
                identity=identity,
                tool=tool,
                tool_id=tool_id,
                input_digest=input_digest,
            )
        self._record(receipt)
        return enriched
