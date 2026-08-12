# Abyss Machine MCP Design

## Thesis

The stable dependency direction is:

```text
agent intent -> abyss-machine MCP read contour -> abyss-machine owner route
             -> cited owner evidence -> separately authorized owner action
```

MCP is weaker than `/etc/abyss-machine` source contracts,
`/var/lib/abyss-machine` evidence, owner validators, and operator intent.

## Ownership

`abyss-machine` owns host facts, policies, generated state, hardware evidence,
resource planning, nervous and typing state, and mutation gates.
`abyss-stack` owns the MCP package, loopback topology, and lifecycle packaging.
`aoa-memo` owns reviewed memory; `aoa-evals` owns proof and verdict authority.

## Effect classification

The adapter classifies the executed owner command, not the user-facing noun.
A status, recall, trace, coverage, or validation route is effectful when its
CLI implementation refreshes a latest file, history, cache, evidence pack, or
index.

The read contour therefore uses a finite allowlist:

- existing projections: stack-bridge latest, process latest, change latest,
  and RAG latest;
- source/static reads: bridge, maps paths/policy, and RAG paths/policy;
- explicitly non-persistent live reads: memory status/pressure/plan, typing
  status/causal-context, maps query/packet;
- preflight: resource plan with mandatory `--no-write`;
- artifact registry reads: trust gate and registry latest.

All other historical names are denied before the command runner. The denied
set is returned by the surface catalog so removal is observable rather than
silent.

## Composite tools

The fast brief reads only `stack-bridge latest`. Live/full briefs add safe
memory, typing, process-latest, and changes-latest surfaces.

The typing surface requests the owner-provided compact status projection so a
session read does not first materialize and parse the full detailed packet. A
legacy full-status retry is allowed only for the exact argparse signal that the
installed owner CLI predates `--compact`; other failures remain failures, and
the fallback is visible in the returned MCP packet.

`abyss_machine_route()` combines resource plan in no-write mode, memory plan,
and the existing bridge constraints. It does not invoke the effectful
`processes game-guard` CLI route; memory plan already computes its owner input
transitively with `write_latest=False`.

Maps queries and context packets remain navigation signals. `rag-latest` reads
an existing trace; creating a RAG trace is an internal effect and is not
available from this MCP.

## Process and credential boundary

The HTTP read process has a dedicated bearer, scope, and client identity. Its
systemd unit has `ProtectSystem=strict`, `ProtectHome=read-only`, no persistent
writable path, and only loopback networking. A future internal-effect MCP
requires a different process, credential, filesystem allowlist, catalog,
approval policy, receipt, postcondition, and rollback route. It must not be
added to this server by conditional code reachable with the read credential.

## Readiness

The source contour is ready for a canary only when:

- the server catalog contains no effectful tool;
- every generic surface name is checked against the read allowlist;
- withdrawn names fail before command dispatch;
- resource preflight always carries `--no-write`;
- owner-specific authentication cannot be substituted with another organ
  bearer;
- the managed read unit has no persistent writable path;
- source-local tests and live read validation pass.

Those checks establish source correctness, not deployment, registration,
observed invocation, benefit, or maturity.
