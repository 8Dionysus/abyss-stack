# Design

## Purpose

Agents need stack-owned runtime evidence without granting the stack semantic
authority over the direct owner adapters it operates.

The package therefore consumes one typed observation with explicit links:

```text
source
  -> package
  -> deploy
  -> process
  -> endpoint
  -> registry
  -> consumer schema observation
  -> grounded canary
  -> rollback evidence
```

Every link keeps its own state, timestamp, expiry, evidence refs, and reason
codes. Process activity is not endpoint readiness; endpoint readiness is not
owner-result freshness; consumer registration is not schema compatibility.
Plan preparation therefore accepts only `exact` or `compatible_drift`
freshness. Activation also requires process and endpoint readiness, an exact
consumer/server schema match, at least one shared protocol version, grounded
canary evidence, and rollback readiness.
The compatible consumer is selected deterministically and its registration
reference becomes the exact activation-step target. Candidate expiry is capped
by every link and evidence ref actually copied into the plan, including
freshness evidence.

## Progressive surface

Catalog results are compact and deliberately omit detailed schemas. Inspection
loads one owner/policy subject and one view. A separate candidate process can
compile one bounded plan against the exact observation digest. No call invokes
an owner server or runtime lifecycle command.

## Authority

`abyss-stack` owns the observation and runtime-plan shape. Owner repositories
own capability and payload meaning. `aoa-sdk` owns registry discovery and
activation-plan compilation. `aoa-evals` owns central proof interpretation.
The named acceptance owner accepts durable source or memory changes.

The MCP stable production line remains `2025-11-25`. These contracts are
protocol-independent so a future adapter can coexist without changing runtime
authority.

Managed units execute a stack-owned, source-addressed virtual environment under
`Services/abyss-stack-mcp`; they never inherit dependencies from ambient
Python. Provisioning is explicit and does not start or register either plane.

Published JSON Schema carries all structurally expressible conditional model
invariants. Runtime Pydantic validation additionally owns cross-field time
ordering, uniqueness, and content-address verification.
