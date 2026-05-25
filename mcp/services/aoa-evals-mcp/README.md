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
- what report skeleton can be prepared without computing a verdict.

## Source Hierarchy

| Layer | Role |
| --- | --- |
| `aoa-evals` source bundle | bounded claim, object under evaluation, verdict logic, blind spots, and report contract |
| `aoa-evals/generated/` | catalog, capsule, section, comparison, and report read models |
| `aoa-evals` runtime-candidate readers | candidate evidence and artifact hook templates |
| `abyss-stack/Logs/eval-exports` | private runtime candidate exports produced by governed execution |
| `aoa-evals-mcp` | live read-only MCP access plane over those surfaces |

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

Prompts:

- `eval-select`
- `eval-find-or-propose`
- `eval-review`
- `evidence-packet`
- `report-skeleton`

Selection, find-or-propose, inspection, expansion, comparison,
evidence-template, runtime export, and skeleton tools are read-only. They do
not run evals, compute verdicts, publish receipts, promote bundles, ingest or
accept evidence, approve proposals, create bundles, or mutate `aoa-evals`.

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
