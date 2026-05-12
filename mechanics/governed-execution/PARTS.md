# Governed Execution Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Governed runner | `parts/governed-runner/` | `scripts/aoa-governed-run`, `scripts/_aoa_governed_execution.py` |
| Autonomy status | `parts/autonomy-status/` | `scripts/aoa-status`, `scripts/_aoa_status_autonomy.py` |
| Return policy | `parts/return-policy/` | `config-templates/Configs/agent-api/return-policy.yaml`, `parts/return-policy/schemas/`, `parts/return-policy/examples/`, `mechanics/governed-execution/docs/GOVERNED_EXECUTION.md` |
| Runtime contracts | `parts/runtime-contracts/` | governed execution schemas and focused tests |
| Candidate exports | `parts/candidate-exports/` | export scripts, candidate schemas, examples, and focused tests |
| Local worker path | `parts/local-worker-path/` | `mechanics/inference-pilots/docs/LANGGRAPH_PILOT.md`, `mechanics/inference-pilots/legacy/raw/W5_PILOT.md`, `mechanics/inference-pilots/legacy/raw/W6_PILOT.md` |

Keep these parts together: if governed execution request, policy, canary, or
review behavior changes, update schemas, scripts, validators, and tests in the
same pass.
