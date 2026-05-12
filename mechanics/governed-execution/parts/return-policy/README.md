# Return Policy

Routes `config-templates/Configs/agent-api/return-policy.yaml` and
`mechanics/governed-execution/docs/GOVERNED_EXECUTION.md`.

Policy templates remain deployment inputs; active contracts live under
this part:

- `schemas/runtime-return-policy.schema.json`
- `schemas/runtime-return-event.schema.json`
- `examples/runtime_return_policy.agentic-local.example.json`
- `examples/runtime_return_event.workhorse-local.example.json`

`parts/runtime-contracts/` owns governed-execution request and policy
contracts. This part owns the return-policy surface that runtime wrappers and
status readouts consume.
