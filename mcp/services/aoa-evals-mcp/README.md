# aoa-evals-mcp

`aoa-evals-mcp` exposes `aoa-evals` bounded proof surfaces through two
process-isolated MCP contours:

- read on `127.0.0.1:5424`, with
  `aoa-evals-mcp-read-bearer-token` and `mcp:aoa-evals:read`;
- candidate on `127.0.0.1:5435`, with the distinct
  `aoa-evals-mcp-candidate-bearer-token` and
  `mcp:aoa-evals:candidate`.

The read catalog contains all resources and non-persistent tools. The
candidate catalog contains only the three gated local-port writer tools and no
resources.

For organ admission, the historical complete catalogs are narrowed by
`AOA_EVALS_MCP_CAPABILITY_PROFILE` and bound fail-closed to the owner manifest
`aoa-evals:docs/architecture/aoa_evals_mcp_capabilities.v1.json`:

- `eval-discovery-read`: four source-linked discovery/freshness tools plus two
  static resources and two resource templates;
- `eval-request-prepare`: one non-persistent typed request-candidate tool;
- `proof-result-read`: one tool and one resource template for an already issued
  indexed bundle-local report.

The proof-result profile reads owner-issued proof; it never runs an eval,
computes or publishes a verdict, accepts evidence, or infers admission. Stdio
keeps the complete compatibility catalog unless a profile is explicit.
Request preparation does not scan the stack runtime-export lane implicitly;
explicit evidence refs remain visible in the typed proposal without turning a
request-shaping call into broad private candidate discovery.

It does not replace `aoa-evals`, generated readers, bundle-local review, or
runtime-candidate contracts. It gives agents one repeatable route to ask:

- which bounded eval applies;
- whether missing proof pressure should route to an existing eval, candidate
  evidence, a quest record, or a repo-local `eval_need_v1` draft;
- what this bundle claims and does not claim;
- which generated section or comparison read model matters;
- what candidate runtime evidence template fits;
- whether source or approved mirror readers are fresh enough to use;
- what the current Eval Forge front door exposes for a new eval session;
- whether a candidate evidence packet is schema-shaped and review-routed;
- which stack-owned private runtime candidate exports are waiting for review;
- which sibling repositories expose repo-local `evals/` ports;
- which OS Abyss Git roots are missing, skeleton, active, invalid, or stale
  local-port candidates;
- whether local eval pressure should stay local or route toward central
  `aoa-evals`;
- what report skeleton can be prepared without computing a verdict.

## Source Hierarchy

| Layer | Role |
| --- | --- |
| `aoa-evals` source bundle | bounded claim, object under evaluation, verdict logic, blind spots, and report contract |
| `aoa-evals/generated/` | catalog, capsule, section, comparison, and report read models |
| `aoa-evals` runtime-candidate readers | candidate evidence and artifact hook templates |
| `aoa-evals` readiness dashboard | Eval Forge front-door refs, commands, candidate queue routes, and non-proof stop lines |
| `abyss-stack/Logs/eval-exports` | private runtime candidate exports produced by governed execution |
| sibling repo `evals/` ports | repo-local eval pressure, suite notes, execution sidecars, report notes, and intake drafts |
| `aoa-evals-mcp` | live MCP access plane over those surfaces, with narrow local-port write gates |

## MCP Surface

Read-contour resources:

- `aoa-evals://catalog`
- `aoa-evals://bundle/{name}`
- `aoa-evals://bundle/{name}/sections`
- `aoa-evals://comparison-spine`
- `aoa-evals://runtime-candidate-templates`
- `aoa-evals://runtime-status`
- `aoa-evals://forge-access`
- `aoa-evals://runtime-evidence/schema`
- `aoa-evals://runtime-candidate-exports`
- `aoa-evals://runtime-candidate-export/{record_id}`
- `aoa-evals://reports`
- `aoa-evals://local-ports`
- `aoa-evals://local-port/{repo}`
- `aoa-evals://local-port/{repo}/intake`
- `aoa-evals://local-port/{repo}/suites`
- `aoa-evals://local-port/{repo}/reports`

Read-contour tools:

- `aoa_evals_select(proof_question, filters)`
- `aoa_evals_find_or_propose(proof_question, proposal)`
- `aoa_evals_inspect(name)`
- `aoa_evals_expand(name, section_key)`
- `aoa_evals_comparison(baseline_mode)`
- `aoa_evals_runtime_evidence_template(name)`
- `aoa_evals_runtime_status()`
- `aoa_evals_forge_access_packet()`
- `aoa_evals_validate_evidence_candidate(packet)`
- `aoa_evals_runtime_candidate_exports(limit)`
- `aoa_evals_read_runtime_candidate_export(record_id, include_payload)`
- `aoa_evals_report_skeleton(name, evidence_refs)`
- `aoa_evals_local_ports(status, include_skeleton)`
- `aoa_evals_local_port(repo)`
- `aoa_evals_find_or_propose_local(repo, proof_question, proposal)`

Profile-only tools:

- `aoa_evals_prepare_request_candidate(proof_question, proposal)` on
  `eval-request-prepare`;
- `aoa_evals_read_proof_result(report_id)` on `proof-result-read`.

Profile-only resource template:

- `aoa-evals://proof-result/{report_id}` on `proof-result-read`.
Candidate-contour tools:

- `aoa_evals_write_local_intake(repo, packet, file_slug, apply, replace_existing)`
- `aoa_evals_write_local_suite_note(repo, suite_slug, title, summary, body_markdown, refs, apply, replace_existing)`
- `aoa_evals_write_local_report_note(repo, report_slug, title, summary, body_markdown, refs, apply, replace_existing)`

Read prompts:

- `eval-select`
- `eval-find-or-propose`
- `eval-review`
- `evidence-packet`
- `eval-forge-access`
- `local-eval-port`
- `report-skeleton`

The candidate contour exposes only `local-eval-port-write`.

Selection, find-or-propose, inspection, expansion, comparison,
evidence-template, runtime export, local-port inspection, and skeleton tools are
read-only. Local write tools are gated by `apply=false` by default and may only
write repo-local `evals/intake/*.eval_need.json`,
`evals/suites/*.suite.md`, `evals/reports/*.report.md`, and the matching
`PORT.yaml` activation from `skeleton` to `active`.
Every write response includes a `write_receipt` that records dry-run/apply
state, target path confinement, allowed local-port globs, validation issues,
`PORT.yaml` activation, side effects, and the explicit absence of proof
authority, promotion, central mutation, verdicts, or scoring.
Managed candidate startup additionally requires the selected port under
`AOA_EVALS_MCP_CANDIDATE_ROOTS`. The systemd sandbox makes only each admitted
port's `intake/`, `suites/`, `reports/`, and `PORT.yaml` writable. Suite
execution sidecars remain read-only even inside the candidate process.

The service does not run evals, compute verdicts, publish receipts, promote
bundles, ingest or accept evidence, approve proposals, create central bundles,
or mutate `aoa-evals`.

Local suite execution sidecars are inspect-only through MCP. A `ready` suite
means only that the current `aoa-evals` owner builder found a fresh reviewed
source contract. MCP forces execution, proof, promotion, runtime
reproducibility, and sidecar-write authority off; it never invokes
`runner.argv`. The repo owner or `aoa-eval-apply` must JIT-revalidate the
sidecar and tracked hashes, capture the environment, and write an execution
receipt before any separate owner-local run.

`aoa_evals_forge_access_packet` and `aoa-evals://forge-access` expose the
current Eval Forge front door as access-plane data: selected `aoa-evals` root
and freshness state, readiness summary, active local-port routes, candidate
queue hints, Forge docs refs, exact route commands, stop-lines, and explicit
non-proof fields. The packet is read-only and candidate-only; it cannot write
worksheets, local ports, central bundles, verdicts, scores, receipts, or proof
promotion.

`aoa_evals_local_ports` is an OS Abyss-wide routing inventory, not just a list
of present `PORT.yaml` files. It scans Git roots below the workspace, skips
runtime-heavy and worktree paths, excludes `aoa-evals` as the central proof
owner, and returns `inventory_status`, `pressure_counts`,
`validation_issues`, `central_eval_name_matches`, and `route_recommendation`.
Those recommendations are advisory routing evidence; direct repo inspection and
central `aoa-evals` review still own any mutation or proof adoption.
The current inventory shape is locked to
`aoa-evals:docs/architecture/local_eval_port_inventory.contract.v2.json` and
is produced through the selected `aoa-evals` source checkout. MCP accepts the
historical v1 contract for compatibility, but v1, unknown, invalid-authority,
or degraded fallback input always maps suite execution to `absent`; suite-note
counts never imply runnable posture. MCP reports producer/compatibility
metadata and treats a missing or failed owner builder as a degraded read path,
not as a new source of truth.

In the shared AoA Codex plane this service is registered as `aoa_evals` through
`8Dionysus:config/codex_plane/runtime_manifest.v1.json`. The workspace launcher
is `<workspace-root>/.codex/bin/aoa-evals-mcp-server.py`; it resolves this
stack-owned service without making `8Dionysus` the service authority.
Managed read and candidate units select disjoint catalogs through
`AOA_MCP_POLICY_FAMILY`. Stdio defaults to read and candidate must be explicit.
When installed as a package, the direct server entry point is
`aoa-evals-mcp-server`; `aoa-evals-mcp` remains the CLI entry point.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
