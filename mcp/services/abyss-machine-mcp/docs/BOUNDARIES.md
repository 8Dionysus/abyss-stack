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

The fast brief reads the existing `stack-bridge latest`; it never refreshes the
bridge. Targeted surfaces execute only commands in the read catalog.

Artifact trust access is limited to trust-gate and registry-latest reads.
Requirements, producer profiles, affected/drift, coverage, scenarios, and
validation currently persist generated state in the owner CLI and are denied.

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
- No cache, latest, index, trace, eval, evidence-pack, or validation refresh.
- No reuse of another organ's read bearer or the transitional shared bearer.
- No exposure beyond portable stdio or the decision-bound authenticated
  loopback shared HTTP owner; remote, wildcard-bind, gateway, or proxy
  exposure requires a later decision.
