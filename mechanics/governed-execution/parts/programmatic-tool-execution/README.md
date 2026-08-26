# Programmatic Tool Execution

This part owns the runtime boundary for the provider-neutral
`aoa_programmatic_tool_execution_v1` contract. It dispatches an explicitly
admitted request to one registered adapter, validates the returned observation,
and sends only validated runtime evidence to an optional sink.

The runtime is disabled by default. `CodexCodeModeHostAdapter` is the first
adapter seam and `LocalModelSubstrateAdapter` is an independent second seam.
Neither adapter launches a host or model here; callers must bind an explicit
runtime invoker after the relevant admission. Provider details stay inside the
concrete adapter.

This part does not own provider discovery, model selection, sandbox
enforcement, eval meaning, promotion, economy policy, or final acceptance.
See [CONTRACT](CONTRACT.md) and [VALIDATION](VALIDATION.md).
