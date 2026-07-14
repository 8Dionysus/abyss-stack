# abyss-machine-mcp

`abyss-machine-mcp` exposes compact local host-machine context through a small
MCP access plane.

It does not replace `abyss-machine`, host source contracts, generated facts,
change ledgers, validators, reviewed memory, or proof authority. It gives
agents one repeatable route to ask:

- what is true about the machine now;
- what constrains action;
- what is safe to do next;
- where the evidence lives;
- which layer owns the truth.

## Source Hierarchy

| Layer | Role |
| --- | --- |
| `/etc/abyss-machine` | host source contracts, policies, route law |
| `/var/lib/abyss-machine` | generated latest facts, indexes, validation output, histories |
| `abyss-machine` CLI | owner command surface and validators |
| `abyss-stack` | runnable MCP package and local transport topology |
| `abyss-machine-mcp` | read-only access plane over host read models |

## MCP Surface

Resources:

- `abyss-machine://brief`
- `abyss-machine://authority`
- `abyss-machine://evidence-map`
- `abyss-machine://stack-bridge`
- `abyss-machine://resource-status`
- `abyss-machine://memory-pressure`
- `abyss-machine://typing-status`
- `abyss-machine://maps`
- `abyss-machine://maps/{axis}`
- `abyss-machine://context-packet/{reader_profile}`
- `abyss-machine://rag`
- `abyss-machine://rag-validate`
- `abyss-machine://surface/{name}`

Tools:

- `abyss_machine_brief(profile, evidence_limit)`
- `abyss_machine_surface(name, query, work_class, kind, scope, mode, axis, reader_profile, limit, evidence_limit)`
- `abyss_machine_evidence_map(layer, limit)`
- `abyss_machine_route(intent, work_class, kind)`
- `abyss_machine_recall(query, mode)`
- `abyss_machine_maps(axis, query, limit)`
- `abyss_machine_context_packet(axis, query, reader_profile, limit)`
- `abyss_machine_rag_trace(query, axis, reader_profile, limit, evidence_limit)`

Prompts:

- `machine-brief`
- `before-heavy-work`
- `typing-context`
- `nervous-recall`
- `machine-atlas`
- `machine-rag-trace`
- `artifact-trust-read`
- `host-incident-triage`

Every response carries an authority boundary and keeps source refs visible.
`abyss_machine_brief` defaults to a small evidence window so agents get a fast
entry map first; use `abyss_machine_evidence_map(limit=N)` to expand refs when
the task needs deeper proof. Outputs are compacted by default so agents do not
flood the prompt with whole bridge archives.

Artifact trust surfaces are available through the same
`abyss_machine_surface` tool, not through a separate MCP server:

- `artifact-trust-requirements`
- `artifact-trust-producer-profiles`
- `artifact-trust-affected`
- `artifact-trust-coverage`
- `artifact-trust-gate`
- `artifact-trust-registry-latest`
- `artifact-trust-scenarios`
- `artifact-trust-validate`

These surfaces wrap allowlisted read-only `abyss-machine artifacts ... --json`
commands. They do not build sidecars, sign, promote evidence, write the
registry, repair state, or approve consumption beyond the returned
`abyss-machine` read model. `artifact-trust-affected` and
`artifact-trust-coverage` accepts optional `source_root`, `source_repo`, and
`source_ref` parameters so agents can inspect explicit dirty source-ref
freshness against a bounded abyss-machine source root instead of relying on the
MCP process working directory. If
the installed `abyss-machine` CLI does not yet support source-context flags for
coverage, the MCP falls back to plain coverage and returns an explicit
`artifact_trust_coverage_source_context_unsupported_by_cli` warning.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
