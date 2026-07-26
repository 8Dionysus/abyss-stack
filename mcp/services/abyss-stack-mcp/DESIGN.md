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
exact current source, package, deployed revision and tree digest, schema,
selected consumer, and canary contour, and acceptance-owner evidence bound to
the exact current source revision and package digest and issued no earlier than
central proof. Effect-policy activation remains blocked until the separate
effect contracts named in the owner decision are modeled; restart cannot serve
as an activation bypass.
The compatible consumer is selected deterministically and its registration
reference becomes the exact activation-step target; central proof and owner
acceptance are separate preceding verification steps. Only after those gates
does a shadow registry receive an admission action addressed to its immutable
ID-and-digest pair; an already admitted entry is verified against the same pair.
Sync and deploy candidates include the exact transition action between preview
or staging and their postcondition check. The source identity supplies the
expected post-sync tree, the package identity supplies the expected
post-deploy tree, and the candidate binds that future digest independently of
the currently observed deploy tree. Rollback denial addresses the immutable
registry ID-and-digest pair. Candidates remain non-executing and require
separate operator approval. Candidate expiry is capped by every link and
evidence ref actually copied into the plan, including freshness, central-proof,
and acceptance evidence. Required evidence timestamps must also be causally
consistent with the enclosing observation snapshot; central proof follows its
canary evidence, proof and acceptance receipts cannot predate their asserted
event beyond the bounded clock skew, and duplicate evidence identities cannot
disagree on `observed_at`.

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
The environment is reproduced from exact direct and transitive pins with
artifact hashes, and its identity binds both deployed source content and the
lock file. Provisioning is explicit, refuses to replace the environment while
either plane is active or its state cannot be observed, and does not stop,
start, or register either plane. After the units are linked and reloaded, each
process holds a shared lock for its lifetime; changed provisioning holds the
exclusive lock and checks stopped state both before building and immediately
before swapping the verified environment.

`rollback_required` is admissible only for the failed source/package/deploy
links of a rollback plan, and only while the triggering link and its evidence
refs remain unexpired. Other unusable states remain blocked, and usable
freshness plus exact rollback evidence are still mandatory.

Published JSON Schema carries all structurally expressible conditional model
invariants. Runtime Pydantic validation additionally owns cross-field time
ordering, uniqueness, and content-address verification.
