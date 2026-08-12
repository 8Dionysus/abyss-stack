# abyss-machine-mcp

`abyss-machine-mcp` is the owner-bounded read contour for host-machine
context. It exposes a finite set of `abyss-machine ... --json` routes that
either read existing state or explicitly select the owner CLI no-write mode.

It does not replace `abyss-machine`, host source contracts, generated facts,
validators, reviewed memory, or proof authority. MCP owns access only.

## Source hierarchy

| Layer | Role |
| --- | --- |
| `/etc/abyss-machine` | host source contracts, policies, route law |
| `/var/lib/abyss-machine` | generated latest facts, indexes, and histories |
| `abyss-machine` CLI | owner command and effect boundary |
| `abyss-stack` | runnable MCP package and local transport topology |
| `abyss-machine-mcp` | bounded read access over owner routes |

## Read contour

Resources:

- `abyss-machine://brief`
- `abyss-machine://authority`
- `abyss-machine://evidence-map`
- `abyss-machine://stack-bridge`
- `abyss-machine://memory-pressure`
- `abyss-machine://typing-status`
- `abyss-machine://maps`
- `abyss-machine://maps/{axis}`
- `abyss-machine://context-packet/{reader_profile}`
- `abyss-machine://rag`
- `abyss-machine://surfaces`
- `abyss-machine://processes-latest`
- `abyss-machine://changes-latest`
- `abyss-machine://surface/{name}`

Tools:

- `abyss_machine_brief(profile, evidence_limit)`
- `abyss_machine_surface(...)`
- `abyss_machine_surfaces()`
- `abyss_machine_evidence_map(layer, limit)`
- `abyss_machine_route(intent, work_class, kind)`
- `abyss_machine_maps(axis, query, limit)`
- `abyss_machine_context_packet(axis, query, reader_profile, limit)`

Prompts:

- `machine-brief`
- `before-heavy-work`
- `typing-context`
- `machine-atlas`
- `artifact-trust-read`
- `host-incident-triage`

`abyss_machine_surfaces()` is the machine-readable contract. Every admitted
entry has `effect: read` and `persistent_writes: false`. Historical names
whose owner CLI route refreshes or persists state remain in an explicit
withdrawn list and fail before command dispatch.

Important command bindings include:

- `stack-bridge` -> `abyss-machine stack-bridge latest --json`;
- `typing-status` -> `abyss-machine typing status --compact --json`; an older
  owner CLI may fall back to the full status route only when argparse reports
  that the compact flag is unavailable, and the MCP result exposes that
  compatibility fallback;
- `resource-plan` -> `abyss-machine resource plan ... --no-write --json`;
- memory status, pressure, and plan -> owner CLI paths that pass
  `write_latest=False`;
- maps query/packet and RAG latest -> reads of existing owner state;
- artifact trust gate and registry latest -> registry reads without refresh.

Nervous recall, RAG trace/eval/validate, generated validators, resource status,
coverage builders, heartbeat pulse, change index, and similar diagnostics are
not read merely because their result is JSON. They currently persist
generated/latest state and are unavailable from this contour. No
`internal_effect` machine MCP is admitted yet.

## Transport and authentication

Stdio remains the portable default. Streamable HTTP is loopback-only and uses
the owner/effect-specific tuple:

- environment: `ABYSS_MACHINE_MCP_READ_BEARER_TOKEN`;
- systemd credential: `abyss-machine-mcp-read-bearer-token`;
- scope: `mcp:abyss-machine:read`;
- client identity: `aoa-loopback-codex:abyss-machine:read`.

The managed runtime uses `aoa-organ-mcp-read@abyss-machine.service`, whose
filesystem is read-only and which has no `ReadWritePaths`.

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run).
