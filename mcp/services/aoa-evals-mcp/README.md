# aoa-evals-mcp

`aoa-evals-mcp` exposes `aoa-evals` bounded proof surfaces through a small MCP
access plane.

It does not replace `aoa-evals`, generated readers, bundle-local review, or
runtime-candidate contracts. It gives agents one repeatable route to ask:

- which bounded eval applies;
- whether missing proof pressure should route to an existing eval, candidate
  evidence, a quest record, or a repo-local `eval_need_v1` draft;
- what this bundle claims and does not claim;
- which generated section or comparison read model matters;
- what candidate runtime evidence template fits;
- whether source or approved mirror readers are fresh enough to use;
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
| `abyss-stack/Logs/eval-exports` | private runtime candidate exports produced by governed execution |
| sibling repo `evals/` ports | repo-local eval pressure, suite notes, report notes, and intake drafts |
| `aoa-evals-mcp` | live MCP access plane over those surfaces, with narrow local-port write gates |

## MCP Surface

Resources:

- `aoa-evals://catalog`
- `aoa-evals://bundle/{name}`
- `aoa-evals://bundle/{name}/sections`
- `aoa-evals://comparison-spine`
- `aoa-evals://runtime-candidate-templates`
- `aoa-evals://runtime-status`
- `aoa-evals://runtime-evidence/schema`
- `aoa-evals://runtime-candidate-exports`
- `aoa-evals://runtime-candidate-export/{record_id}`
- `aoa-evals://reports`
- `aoa-evals://local-ports`
- `aoa-evals://local-port/{repo}`
- `aoa-evals://local-port/{repo}/intake`
- `aoa-evals://local-port/{repo}/suites`
- `aoa-evals://local-port/{repo}/reports`

Tools:

- `aoa_evals_select(proof_question, filters)`
- `aoa_evals_find_or_propose(proof_question, proposal)`
- `aoa_evals_inspect(name)`
- `aoa_evals_expand(name, section_key)`
- `aoa_evals_comparison(baseline_mode)`
- `aoa_evals_runtime_evidence_template(name)`
- `aoa_evals_runtime_status()`
- `aoa_evals_validate_evidence_candidate(packet)`
- `aoa_evals_runtime_candidate_exports(limit)`
- `aoa_evals_read_runtime_candidate_export(record_id, include_payload)`
- `aoa_evals_report_skeleton(name, evidence_refs)`
- `aoa_evals_local_ports(status, include_skeleton)`
- `aoa_evals_local_port(repo)`
- `aoa_evals_find_or_propose_local(repo, proof_question, proposal)`
- `aoa_evals_write_local_intake(repo, packet, file_slug, apply, replace_existing)`
- `aoa_evals_write_local_suite_note(repo, suite_slug, title, summary, body_markdown, refs, apply, replace_existing)`
- `aoa_evals_write_local_report_note(repo, report_slug, title, summary, body_markdown, refs, apply, replace_existing)`

Prompts:

- `eval-select`
- `eval-find-or-propose`
- `eval-review`
- `evidence-packet`
- `local-eval-port`
- `report-skeleton`

Selection, find-or-propose, inspection, expansion, comparison,
evidence-template, runtime export, local-port inspection, and skeleton tools are
read-only. Local write tools are gated by `apply=false` by default and may only
write repo-local `evals/intake/*.eval_need.json`,
`evals/suites/*.suite.md`, `evals/reports/*.report.md`, and the matching
`PORT.yaml` activation from `skeleton` to `active`.

The service does not run evals, compute verdicts, publish receipts, promote
bundles, ingest or accept evidence, approve proposals, create central bundles,
or mutate `aoa-evals`.

`aoa_evals_local_ports` is an OS Abyss-wide routing inventory, not just a list
of present `PORT.yaml` files. It scans Git roots below the workspace, skips
runtime-heavy and worktree paths, excludes `aoa-evals` as the central proof
owner, and returns `inventory_status`, `pressure_counts`,
`validation_issues`, `central_eval_name_matches`, and `route_recommendation`.
Those recommendations are advisory routing evidence; direct repo inspection and
central `aoa-evals` review still own any mutation or proof adoption.
The inventory shape is locked to
`aoa-evals:docs/architecture/local_eval_port_inventory.contract.v1.json`;
MCP reports the loaded contract metadata and treats missing contract data as a
degraded fallback, not as a new source of truth.

In the shared AoA Codex plane this service is registered as `aoa_evals` through
`8Dionysus:config/codex_plane/runtime_manifest.v1.json`. The workspace launcher
is `<workspace-root>/.codex/bin/aoa-evals-mcp-server.py`; it resolves this
stack-owned service without making `8Dionysus` the service authority.
When installed as a package, the direct server entry point is
`aoa-evals-mcp-server`; `aoa-evals-mcp` remains the CLI entry point.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
