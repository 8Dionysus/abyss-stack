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
  -> central proof observation
  -> owner acceptance observation
  -> grounded canary
  -> rollback evidence
```

Every link keeps its own state, timestamp, expiry, evidence refs, and reason
codes. Process activity is not endpoint readiness; endpoint readiness is not
owner-result freshness; consumer registration is not schema compatibility.
Plan preparation therefore accepts only `exact` or `compatible_drift`
freshness. Activation also requires process and endpoint readiness, an exact
consumer/server schema match, at least one shared protocol version, grounded
canary evidence, rollback readiness, a passed proof-owner verdict bound to the
exact current source/package/deploy/schema/selected-consumer/canary contour,
and acceptance-owner evidence bound to the exact current source revision and
package digest and issued no earlier than central proof.
The compatible consumer is selected deterministically and its registration
reference becomes the exact activation-step target; central proof and owner
acceptance are separate preceding verification steps. Only after those gates
does a shadow registry receive an admission action; an already admitted entry
is verified instead. Candidate expiry is capped by every link and evidence ref
actually copied into the plan, including freshness, central-proof, and
acceptance evidence. Required evidence timestamps must also be causally
consistent with the enclosing observation snapshot; central proof follows its
canary evidence, and duplicate evidence identities cannot disagree on
`observed_at`.

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
Python or import newly synced `Configs/src` over the installed package.
Provisioning is explicit and does not start or register either plane.

`rollback_required` is admissible only for the failed source/package/deploy
links of a rollback plan, and only while the triggering link and its evidence
refs remain unexpired. Other unusable states remain blocked, and usable
freshness plus exact rollback evidence are still mandatory.

Published JSON Schema carries all structurally expressible conditional model
invariants. Runtime Pydantic validation additionally owns cross-field time
ordering, uniqueness, and content-address verification.
