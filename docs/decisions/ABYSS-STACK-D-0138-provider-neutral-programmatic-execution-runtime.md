# Provider-Neutral Programmatic Execution Runtime

- Decision ID: ABYSS-STACK-D-0138
- Status: accepted
- Date: 2026-08-26
- Owner surface: `mechanics/governed-execution/parts/programmatic-tool-execution/`

## Index Metadata

- Original date: 2026-08-26
- Surface classes: runtime boundary, adapter protocol, observation
- Stack lanes: governed execution, runtime evidence
- Mechanic parents: governed-execution
- Guard families: explicit admission, default-off activation, observation integrity
- Posture: accepted runtime seam

## Context

Direction 4 needs one stack-owned runtime boundary for the SDK's provider-neutral
programmatic tool execution contract. Existing governed execution owns runtime
admission and evidence, while provider-specific launches must remain behind
explicit adapters.

## Options considered

- Add provider-specific behavior to the existing Agent OS bridge.
- Let each provider expose an unrelated runtime request and observation shape.
- Add one governed runtime seam with independently registered Codex and local
  substrate adapters.

## Decision

Add `ProgrammaticExecutionRuntime` under governed-execution. It requires SDK
admission, remains disabled by default, dispatches only to an adapter registered
under the exact request `adapter_id`, validates the returned observation, and
passes only validated evidence to the runtime sink. Provide
`CodexCodeModeHostAdapter` and `LocalModelSubstrateAdapter` as independent
adapter seams without launching either provider in this source slice.

## Rationale

The runtime can preserve exact identity, effect ceilings, explicit missingness,
and evidence ordering while keeping Codex and local-model details out of the
shared ABI. Source presence therefore cannot silently activate provider work.

## Consequences

- The runtime part is testable without a host process, model, network, or live
  baseline.
- A future activation must supply explicit admission and concrete invokers for
  both adapter lanes.
- Runtime observations remain evidence; eval verdicts, promotion, economy
  claims, closeout, and owner acceptance remain separate owner decisions.

## Source surfaces

- `mechanics/governed-execution/parts/programmatic-tool-execution/programmatic_tool_execution.py`
- `mechanics/governed-execution/parts/programmatic-tool-execution/tests/test_programmatic_tool_execution.py`
- `mechanics/governed-execution/README.md`
- `mechanics/governed-execution/PARTS.md`
- `scripts/validators/mechanics_topology.py`
- `scripts/validators/source_structure.py`

## Follow-up route

After paired baseline admission, bind real Codex and local-model invokers under
their owner runtime profiles, collect paired observations, and route them to
`aoa-evals` for a bounded verdict. Do not infer promotion from this runtime
seam or its focused tests.
