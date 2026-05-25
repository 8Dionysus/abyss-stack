# Boundaries

## Authority Split

| Context | Owns | Does not own |
| --- | --- | --- |
| `abyss-machine` | host facts, source contracts, policies, generated latest files, validators, change ledger, bridge contracts | stack MCP packaging |
| `abyss-machine-mcp` | compact read-only access, route prompts, allowlisted surface adapters, evidence refs | host policy, mutation authority, arbitrary commands, private raw capture interpretation |
| `abyss-stack` | runnable MCP package, stdio topology, stack-side decision record | host facts or host source truth |
| `aoa-memo` | durable reviewed memory | live host truth |
| `aoa-evals` | proof and verdict authority | host or stack runtime state |

## Interface

`abyss-machine-mcp` reads `abyss-machine ... --json` outputs from a fixed
allowlist. It returns compact JSON objects with source refs and explicit
authority boundaries.

The fast brief reads `stack-bridge`, which is an owner-routed bridge contract
and evidence map. Targeted surfaces read one live command at a time.

Generated latest files and bridge refs are evidence. They help agents route
work, but they are weaker than source contracts under `/etc/abyss-machine` and
operator intent.

## Stop Lines

- No arbitrary shell command execution.
- No privileged commands.
- No service restart or process mutation.
- No source mutation in `abyss-machine`, `abyss-stack`, AoA repos, work roots,
  or game roots.
- No private raw capture reads by default.
- No memory landing, proof verdict, or evidence acceptance.
- No non-stdio exposure without a later decision.
