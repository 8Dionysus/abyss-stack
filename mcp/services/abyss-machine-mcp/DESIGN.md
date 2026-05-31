# Abyss Machine MCP Design

## Thesis

Agents should be able to ask the machine one compact question before acting:

```text
what is true now, what constrains action, what is safe next, where is evidence,
and which owner layer decides?
```

The stable form is:

```text
agent intent -> abyss_machine MCP -> abyss-machine bridge/read-models -> owner-routed action
```

MCP is the access layer. It is intentionally weaker than `/etc/abyss-machine`
source contracts, `/var/lib/abyss-machine` generated facts, host validators,
and operator intent.

## Contexts

`abyss-machine` owns host facts, local policies, generated latest files,
hardware evidence, typed-text intake state, nervous read models, resource
planning, heartbeats, reactions, responses, and change-ledger routes.

`abyss-stack` owns the runnable MCP package and stdio service topology.

`aoa-memo` owns reviewed memory. `aoa-evals` owns proof and verdict authority.

`abyss-machine-mcp` owns compact access, source refs, route prompts, and safe
read adapters over existing `abyss-machine` JSON commands.

## Operation

An agent can start with:

```text
abyss_machine_brief(profile="fast")
```

The fast brief reads `abyss-machine stack-bridge --json` and returns:

- bridge status and timestamp;
- owner layer map;
- protected roots and non-claims;
- handoff rules;
- mutation gates;
- compact evidence refs;
- safe next-route hints.

The default brief keeps only the first small evidence window. Agents expand
with `abyss_machine_evidence_map(limit=N)` instead of forcing every task to
carry the whole bridge map.

When a task needs targeted live context, the agent uses allowlisted surfaces:

```text
abyss_machine_surface(name="memory-pressure")
abyss_machine_surface(name="typing-status")
abyss_machine_surface(name="resource-status")
abyss_machine_surface(name="processes-game-guard")
```

For launch or mutation posture, the agent uses:

```text
abyss_machine_route(intent, work_class, kind)
```

That route reads resource, memory, game guard, and bridge constraints. It does
not launch anything and does not approve mutation. It returns preflight routes
and evidence pointers.

For focused local recall:

```text
abyss_machine_recall(query)
```

The recall route wraps `abyss-machine nervous recall --json` and keeps the
result as evidence. It does not interpret raw private captures as operator
intent.

For machine self-atlas orientation:

```text
abyss_machine_maps(axis="by-freshness", query="semantic")
abyss_machine_context_packet(axis="by-eval-packet", reader_profile="proof-context")
abyss_machine_rag_trace(query="machine RAG trace loop")
```

The maps route wraps `abyss-machine maps query --json` and returns bounded
route entries from the generated atlas. It is a navigation surface for
freshness, owner routes, RAG/eval/memo/KAG boundary context, and causal
correlation; it does not promote entries into source truth, proof verdicts,
durable memory, or permission to act. The context-packet route wraps
`abyss-machine maps packet --json`; packet shape and authority stay host-owned,
while MCP only transports a bounded reader-profile lens for the current agent.
Reader profiles are not destinations and do not deliver machine moments into
AoA organs.

The RAG trace route wraps `abyss-machine rag trace --json`. It runs the
host-owned read-only loop from maps context packet to bounded evidence
summaries, deterministic answer trace, and local trace eval. MCP transports the
compact result; it does not become proof authority, reviewed memory, KAG truth,
operator authorization, or a repository mutation route.

## Command Policy

The service has a fixed allowlist of `abyss-machine ... --json` read-model
commands. No MCP caller can supply an arbitrary command line.

Allowed surfaces are read-only or preflight-only:

- `stack-bridge`
- `bridge`
- `resource-status`
- `resource-plan`
- `memory-status`
- `memory-pressure`
- `memory-plan`
- `storage-pressure`
- `processes-game-guard`
- `typing-status`
- `typing-coverage`
- `typing-causal-context`
- `nervous-status`
- `nervous-brief`
- `nervous-recall`
- `maps-paths`
- `maps-policy`
- `maps-query`
- `maps-packet`
- `maps-validate`
- `rag-paths`
- `rag-policy`
- `rag-trace`
- `rag-latest`
- `rag-eval`
- `rag-validate`
- `ai-llm-registry`
- `ai-llm-resident-status`
- `heartbeats-pulse`
- `changes-status`
- `changes-index`
- `stack-bridge-validate`

Privileged commands, source mutation, repair, service restart, process
mutation, cleanup, capture deletion, and arbitrary shell execution are outside
this MCP surface.

## Readiness

The first layer is ready when:

- resources, tools, prompts, CLI, and service-local tests exist;
- the fast brief returns a compact owner-aware machine map;
- evidence refs point to existing `abyss-machine` latest/contract files;
- allowed surfaces are typed, bounded, and compacted;
- arbitrary command names are rejected;
- route planning remains non-mutating and points to preflight gates;
- package validation passes against live `abyss-machine` commands.
