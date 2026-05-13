# Return Policy

Routes `config-templates/Configs/agent-api/return-policy.yaml` and
`mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md`.

Policy templates remain deployment inputs; active contracts live under
this part:

- `schemas/runtime-return-policy.schema.json`
- `schemas/runtime-return-event.schema.json`
- `examples/runtime_return_policy.agentic-local.example.json`
- `examples/runtime_return_event.workhorse-local.example.json`

`parts/runtime-contracts/` owns governed-execution request and policy
contracts. `parts/governed-runner/docs/GOVERNED_EXECUTION.md` owns the runner
flow. This part owns the return-policy surface that runtime wrappers and status
readouts consume.
