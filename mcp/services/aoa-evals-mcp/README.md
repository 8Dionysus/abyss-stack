# aoa-evals-mcp

`aoa-evals-mcp` exposes `aoa-evals` bounded proof surfaces through a small MCP
access plane.

It does not replace `aoa-evals`, generated readers, bundle-local review, or
runtime-candidate contracts. It gives agents one repeatable route to ask:

- which bounded eval applies;
- what this bundle claims and does not claim;
- which generated section or comparison read model matters;
- what candidate runtime evidence template fits;
- what report skeleton can be prepared without computing a verdict.

## Source Hierarchy

| Layer | Role |
| --- | --- |
| `aoa-evals` source bundle | bounded claim, object under evaluation, verdict logic, blind spots, and report contract |
| `aoa-evals/generated/` | catalog, capsule, section, comparison, and report read models |
| `aoa-evals` runtime-candidate readers | candidate evidence and artifact hook templates |
| `aoa-evals-mcp` | live read-only MCP access plane over those surfaces |

## MCP Surface

Resources:

- `aoa-evals://catalog`
- `aoa-evals://bundle/{name}`
- `aoa-evals://bundle/{name}/sections`
- `aoa-evals://comparison-spine`
- `aoa-evals://runtime-candidate-templates`
- `aoa-evals://reports`

Tools:

- `aoa_evals_select(proof_question, filters)`
- `aoa_evals_inspect(name)`
- `aoa_evals_expand(name, section_key)`
- `aoa_evals_comparison(baseline_mode)`
- `aoa_evals_runtime_evidence_template(name)`
- `aoa_evals_report_skeleton(name, evidence_refs)`

Prompts:

- `eval-select`
- `eval-review`
- `evidence-packet`
- `report-skeleton`

Selection, inspection, expansion, comparison, evidence-template, and skeleton
tools are read-only. They do not run evals, compute verdicts, publish receipts,
promote bundles, or mutate `aoa-evals`.

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
