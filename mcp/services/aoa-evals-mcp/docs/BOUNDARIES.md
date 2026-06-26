# Boundaries

## Authority Split

| Context | Owns | Does not own |
| --- | --- | --- |
| `aoa-evals` | bounded proof bundles, verdict logic, generated reader contracts, runtime-candidate posture | runtime service execution |
| generated readers | deterministic catalog, capsule, section, comparison, and report read models | proof interpretation stronger than source bundles |
| runtime-candidate readers | candidate evidence and artifact hook templates | accepted proof or verdicts |
| `aoa-evals-mcp` | read access, selection, find-or-propose routing, inspection, expansion, comparison, template lookup, runtime status, Eval Forge front-door access packets, candidate packet validation, runtime candidate export read-model, report skeletons, and gated sibling repo-local eval-port writes | eval running, verdict computation, receipt publication, bundle promotion, central `aoa-evals` source mutation, proposal approval, evidence acceptance, worksheet acceptance, arbitrary sibling path mutation |
| `abyss-stack` | runnable MCP package and stdio service topology | proof meaning |

## Interface

`aoa-evals-mcp` reads source/generated `aoa-evals` surfaces or an approved
runtime mirror. It returns compact JSON objects with source refs and explicit
authority boundaries.

Report skeletons are candidates. Runtime evidence templates are candidates.
The bundle-local source files and review guides decide whether evidence can
support a bounded report.

Runtime status is below source truth. It may reveal missing, stale, or
unmanifested mirrors, but a fresh mirror never becomes proof authority.

Eval Forge access packets are below authoring and review. They may surface
operating-path refs, criteria refs, local-port matrix refs, exact route
commands, candidate queue hints, and active local-port routes. They do not
write worksheets, accept candidates, approve owner-review decisions, or create
central/local proof.

Candidate validation is below ingestion. It means a packet is schema-shaped and
review-routed, not accepted evidence.

Find-or-propose is below authoring. It means the service found likely existing
routes or shaped a candidate `eval_need_v1` context. It does not create source
files, approve the proposal, or make duplicate-fit truth.

Runtime candidate export listing is below review. It reads stack-owned private
records under `Logs/eval-exports/`, omits private payloads by default, and
validates nested candidate packet shape for routing only. A readable export is
not accepted proof.

Local-port inventory is below repo mutation and below central proof adoption.
It may classify workspace Git roots and recommend repair, selection, apply, or
stop routes, but it does not decide that a local eval should exist, promote a
local bundle, or replace direct inspection of the target repo before a write.
Its machine-readable status and route vocabulary is consumed from
`aoa-evals`, not authored by `abyss-stack`.

Local-port write tools are below local repo review and below central proof
adoption. They may prepare or apply only `evals/intake/*.eval_need.json`,
`evals/suites/*.suite.md`, `evals/reports/*.report.md`, and first-pressure
`PORT.yaml` activation from `skeleton` to `active`. They default to dry-run,
reject workspace escape and path-like explicit slugs, and require explicit
overwrite permission. Their responses include audit receipts for dry-run/apply
state, target confinement, validation, activation, side effects, and forbidden
proof/promotion/verdict/scoring/central-mutation effects.

## Stop Lines

- No general eval runner.
- No verdict computation.
- No receipt publication.
- No bundle promotion.
- No `aoa-evals` source mutation.
- No proposal approval or source bundle creation.
- No worksheet acceptance or Eval Forge route promotion from MCP.
- No arbitrary sibling path writes outside repo-local `evals/` ports.
- No treating MCP/generated/runtime output as stronger than source bundles.
- No moving proof authority into `abyss-stack`.
