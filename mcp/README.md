# MCP

`mcp/` contains stack-owned Model Context Protocol access planes.

Use this district when an agent needs a live, addressable route into OS Abyss
context without copying owner-layer memory, runtime evidence, or generated
read models into every prompt.

## Districts

| District | Use for |
|---|---|
| [`services/`](services/README.md) | runnable MCP service packages with package-local source, tests, and route cards |

MCP packages are access planes. Their outputs help agents move, but authority
stays with the source owner named by the package.

## Owner-bounded access fabric

The target stack topology keeps one direct adapter family per owner and one
runtime-owned observation plane:

```text
aoa-sdk discovery and activation candidate
  -> direct owner policy plane
  -> owner-specific payload
  -> stack lifecycle and provenance receipt
```

The stack owns package, deploy, process, endpoint, credential delivery,
lifecycle, canary, and rollback evidence. It does not own the domain meaning,
proof verdict, durable memory, or source acceptance exposed by a sibling
adapter.

Admission is not inferred from a package, running process, listener, Codex
registration, schema listing, or successful call. The private SDK registry
must cite reviewed owner records, stack observations, proof evidence, and
acceptance receipts. Direct owner connections remain available; this district
does not become a proxy or semantic mega-gateway.

Capabilities are classified by actual behavior as `observe`, `derive`,
`validate`, `prepare_candidate`, `apply_runtime`, `accept_source`,
`external_emit`, or `external_change`. Admitted execution uses separate
`read`, `candidate`, `internal_effect`, and `external_effect` policy planes.
Higher-effect planes are separate processes and credentials and remain absent
or disabled until their threat model, approval, receipt, and rollback proof
pass.

`abyss-stack-mcp` is the planned stack-owned runtime observation family. Its
read plane reports source-package-deploy-process-endpoint-consumer evidence;
its candidate plane prepares bounded sync, activation, restart, deployment,
and rollback plans. Runtime effects, if later admitted, use a separate process
and credential and never accept sibling source or memory truth.

The current shared bearer lifecycle remains transitional transport evidence.
It does not satisfy admitted effect isolation and must not be used to raise a
route above shadow without the new policy proof.

`aoa-decisions-mcp` is the access plane for the local workspace decision graph:
it auto-refreshes the ignored graph cache before returning search results,
repo slices, decision neighborhoods, or compact packets.

`tos-corpus-mcp` is the access plane for the Tree of Sophia whole-corpus index
and philosophy graph projection: it reads ToS-owned derived resources and
returns graph-review packets without making `abyss-stack` the owner of ToS
meaning.

`aoa-stats-mcp` is the access plane for the federated stats system: it reads
the `aoa-stats` public contracts and inventory plus owner-local root `stats/`
ports without moving statistical or domain meaning into the runtime adapter.
