# Governed Execution Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Governed runner | `parts/governed-runner/` | `scripts/aoa-governed-run`, `mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py`, `mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md`, `mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py` |
| Autonomy status | `parts/autonomy-status/` | `scripts/aoa-status`, `mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py` |
| Return policy | `parts/return-policy/` | `config-templates/Configs/agent-api/return-policy.yaml`, `mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md`, `parts/return-policy/schemas/`, `parts/return-policy/examples/` |
| Runtime contracts | `parts/runtime-contracts/` | governed execution schemas and focused tests |
| Candidate exports | `parts/candidate-exports/` | `scripts/aoa-export-memo-candidate`, `scripts/aoa-export-runtime-evidence-selection`, `scripts/aoa-export-artifact-hook-candidate`, part-local export backends, candidate schemas, examples, and focused tests |
| Local worker path | `parts/local-worker-path/` | `mechanics/governed-execution/parts/local-worker-path/docs/CONTEXT_BUDGET_POLICY.md`, `mechanics/inference-pilots/parts/langgraph-pilot/docs/LANGGRAPH_PILOT.md`, `mechanics/inference-pilots/PROVENANCE.md` |

Keep these parts together: if governed execution request, policy, canary, or
review behavior changes, update schemas, scripts, validators, and tests in the
same pass.
