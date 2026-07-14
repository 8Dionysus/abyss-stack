# Boundaries

## Authority Split

| Context | Owns | Does not own |
| --- | --- | --- |
| `abyss-machine` | host facts, source contracts, policies, generated latest files, validators, change ledger, bridge contracts | stack MCP packaging |
| `abyss-machine-mcp` | compact read-only access, route prompts, allowlisted surface adapters, evidence refs | host policy, mutation authority, arbitrary commands, private raw capture interpretation |
| `abyss-stack` | runnable MCP package, local transport topology, stack-side decision record | host facts or host source truth |
| `aoa-memo` | durable reviewed memory | live host truth |
| `aoa-evals` | proof and verdict authority | host or stack runtime state |

## Interface

`abyss-machine-mcp` reads `abyss-machine ... --json` outputs from a fixed
allowlist. It returns compact JSON objects with source refs and explicit
authority boundaries.

The fast brief reads `stack-bridge`, which is an owner-routed bridge contract
and evidence map. Targeted surfaces read one live command at a time.

Artifact trust surfaces are targeted read models over `abyss-machine artifacts`
commands. They may expose requirements, producer profiles, affected/drift
posture, coverage, trust-gate verdicts, registry latest selection, scenarios,
and validator status. They may not build sidecars, sign, verify, promote,
repair registry state, write evidence, or decide proof verdicts.

Generated latest files, bridge refs, machine atlas map entries, context
packets, and machine RAG traces are evidence. They help agents route work, but
they are weaker than source contracts under `/etc/abyss-machine` and operator
intent.

## Stop Lines

- No arbitrary shell command execution.
- No privileged commands.
- No service restart or process mutation.
- No source mutation in `abyss-machine`, `abyss-stack`, AoA repos, work roots,
  or game roots.
- No private raw capture reads by default.
- No memory landing, proof verdict, or evidence acceptance.
- No artifact signing, sidecar building, evidence promotion, registry writes,
  or trust-root mutation.
- No KAG publication or delivery into AoA organs.
- No exposure beyond portable stdio or the decision-bound loopback-only shared
  HTTP owner; remote, wildcard-bind, gateway, or proxy exposure requires a
  later decision.
