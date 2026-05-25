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
| `abyss-stack` | runnable MCP package and stdio topology |
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
- `abyss-machine://surface/{name}`

Tools:

- `abyss_machine_brief(profile, evidence_limit)`
- `abyss_machine_surface(name, query, work_class, kind, scope, mode)`
- `abyss_machine_evidence_map(layer, limit)`
- `abyss_machine_route(intent, work_class, kind)`
- `abyss_machine_recall(query, mode)`

Prompts:

- `machine-brief`
- `before-heavy-work`
- `typing-context`
- `nervous-recall`
- `host-incident-triage`

Every response carries an authority boundary and keeps source refs visible.
`abyss_machine_brief` defaults to a small evidence window so agents get a fast
entry map first; use `abyss_machine_evidence_map(limit=N)` to expand refs when
the task needs deeper proof. Outputs are compacted by default so agents do not
flood the prompt with whole bridge archives.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
