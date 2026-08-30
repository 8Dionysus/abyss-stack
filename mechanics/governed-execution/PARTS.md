# Governed Execution Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Governed runner | `parts/governed-runner/` | `scripts/aoa-governed-run`, `mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py`, `mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md`, `mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py` |
| Agent OS adapter | `parts/agent-os-adapter/` | `scripts/aoa-agent-os-runtime`, exact runtime profile and binding schemas, durable subprocess bridge, paired `aoa-sdk` integration tests |
| External Codex agent | `parts/external-codex-agent/` | `scripts/aoa-external-actor-bind`, `scripts/aoa-external-codex-agent`, `scripts/aoa-external-codex-incarnation`, `scripts/aoa-external-codex-stasis`, role-first owner admission with pinned `aoa-agents`/`aoa-skills` schemas, content-addressed machine-local runtime installer/status/rollback, incarnation-scoped descendant Codex defaults for operator-visible actors, exact launch/task/profile/state/event/report/result/study/review-preparation schemas, separate Codex process, role-scoped MCPs, observe-only usage metering, durable thread resume with bounded continuity-capsule reinjection, canonical independent-review preparation and A2A-return export, bounded responsibility-movement observation and typed review wake |
| Autonomy status | `parts/autonomy-status/` | `scripts/aoa-status`, `mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py` |
| Return policy | `parts/return-policy/` | `config-templates/Configs/agent-api/return-policy.yaml`, `mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md`, `parts/return-policy/schemas/`, `parts/return-policy/examples/` |
| Runtime contracts | `parts/runtime-contracts/` | governed execution schemas and focused tests |
| Candidate exports | `parts/candidate-exports/` | `scripts/aoa-export-memo-candidate`, `scripts/aoa-export-runtime-evidence-selection`, `scripts/aoa-export-artifact-hook-candidate`, part-local export backends, candidate schemas, examples, and focused tests |
| Local worker path | `parts/local-worker-path/` | `mechanics/governed-execution/parts/local-worker-path/docs/CONTEXT_BUDGET_POLICY.md`, `mechanics/inference-pilots/parts/langgraph-pilot/docs/LANGGRAPH_PILOT.md`, `mechanics/inference-pilots/PROVENANCE.md` |
| Programmatic tool execution | `parts/programmatic-tool-execution/` | provider-neutral SDK request/observation runtime seam, Codex host adapter, local-model substrate adapter, and validated observation handoff |
| Ephemeral worker | `parts/ephemeral-worker/` | default-off `ephemeral_read_worker_v1` request/result contracts, bounded read implementation, and Codex/local-provider common-ABI adapter profiles |

Keep these parts together: if governed execution request, policy, canary, or
review behavior changes, update schemas, scripts, validators, and tests in the
same pass.
