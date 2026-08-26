# Contract

`ProgrammaticExecutionRuntime` is the stack-owned execution seam for the SDK's
`aoa_programmatic_tool_execution_v1` request and observation types.

## Admission and dispatch

- The request must carry `activation.state="admitted"`, its exact admission
  evidence, and the exact plan/profile bindings required by the SDK contract.
- The runtime's `enabled` flag defaults to `false`; enabling it is a runtime
  configuration change and does not replace request admission.
- The selected `adapter_id` must be registered and must match the adapter's
  declared identity. A missing or mismatched adapter fails closed.
- The adapter returns a typed observation. The runtime validates exact request
  identity, tool handles, effect ceiling, observation dimensions, and explicit
  missingness before invoking the observation sink.
- A bound adapter exception, including a provider-raised runtime boundary error,
  is reported as the stable `adapter_execution_failed` error and carries no
  observation; it is not reclassified as malformed evidence. Once adapter
  execution begins, completion is unknown unless a returned observation proves
  otherwise. The runtime's own pre-invocation errors remain distinct.
- If an adapter returns an invalid observation, the runtime keeps it out of the
  sink and reports `invalid_observation` as a post-execution or indeterminate
  error: a returned non-null typed observation is attached with
  `execution_completed=True`, while a missing return is marked unknown.
- A sink exception is reported as the stable
  `observation_sink_failed` post-execution error and retains the validated
  observation on the error object, so callers cannot mistake an evidence-store
  failure for an execution failure and blindly retry effects.

## Adapters

- `CodexCodeModeHostAdapter` carries only the exact host reference and a
  caller-bound invoker. It is the first adapter surface; Codex host behavior
  stays behind this class.
- `LocalModelSubstrateAdapter` carries only the exact local route reference
  and a caller-bound invoker. It is independent of the Codex adapter.
- Neither concrete adapter discovers providers, chooses models, starts a
  process, or grants effects. Those concerns require their owner contracts and
  explicit runtime admission.

## Evidence boundary

The optional observation sink receives a record only after SDK validation. A
sink or adapter exception is not converted into success. Returned observations
are runtime evidence; they do not constitute an eval verdict, baseline
admission, promotion, economy claim, closeout, or owner acceptance.
