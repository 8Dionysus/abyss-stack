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
exact current source, package, deployed revision and tree digest, running
process identity, schema, selected consumer, and canary contour, and
acceptance-owner evidence bound to the exact current source revision and
package digest and issued no earlier than central proof. Effect-policy
activation remains blocked until the separate
effect contracts named in the owner decision are modeled; restart cannot serve
as an activation bypass. Restart also verifies and carries a usable central
proof whose source, package, deploy, process, server schema, compatible
consumer registration, canary route, and receipt exactly match the current
subject. The proof-selected consumer evidence is copied into the restart
candidate, so changing any deployed contour cannot reuse an older proof.
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

Before dispatch, a protocol-independent policy seam binds the transport-
verified caller contour to one exact tool and effect class. It applies
canonical request/result size limits, per-process concurrency and sliding-
window rate limits, bounded dispatch deadlines, cancellation propagation,
secret screening, and source-to-sink classification. It returns public-safe
receipts containing only identities, decisions, policy facts, and content
digests. Read results and candidate payloads are always untrusted data with no
instruction authority. The seam has no runtime-effect dispatch path; future
MCP interceptor support may call it but cannot replace it.
An optional persistent sink appends each receipt to one owner/policy-specific
canonical JSONL chain before the in-memory receipt ring is updated. Record IDs
bind the previous ID, sequence, timestamp, contour, and complete validated
receipt. A process restart replays the bounded file and reconstructs only a
public-safe aggregate read model. Raw values are never journalled: only the
same validated identities, policy facts, reason codes, and input/output
digests already present in the receipt. Journal continuity is stack-local
operational evidence, not central proof or owner acceptance.

## Progressive surface

Catalog results are compact and deliberately omit detailed schemas. Inspection
loads one owner/policy subject and one view. A separate candidate process can
compile one bounded plan against the exact observation digest. No call invokes
an owner server or runtime lifecycle command.
Read and candidate bearer contours are distinct values as well as distinct
credential names: provisioning rejects a pre-existing or generated equality
before either contour is considered usable.

Cross-organ host persistence is a separate path:

```text
direct owner result
  -> stack host receipt
  -> exact aoa-sdk transition validation
  -> private immutable snapshot
  -> bounded stack_orchestration_inspect read
```

The stack owns persistence, receipt issuance, and restart-visible state. The
SDK owns transition semantics. Owner calls remain outside both stack MCP
planes, and the read surface never expands the captured owner artifacts.

## Authority

`abyss-stack` owns the observation and runtime-plan shape. Owner repositories
own capability and payload meaning. `aoa-sdk` owns registry discovery and
activation-plan compilation. `aoa-evals` owns central proof interpretation.
The named acceptance owner accepts durable source or memory changes.

The MCP stable production line remains `2025-11-25`. These contracts are
protocol-independent so a future adapter can coexist without changing runtime
authority.

Codex integration consumes this observation through the owner-composed handoff
in `docs/CODEX_CONSUMER_HANDOFF.md`. The stack may issue canary and runtime
rollback-target evidence and carry foreign receipt refs. It never edits the
Codex consumer projection, infers consumer admission, or performs consumer
reload/removal.

Managed units execute a stack-owned, source-addressed virtual environment under
`Services/abyss-stack-mcp`; they never inherit dependencies from ambient
Python or import newly synced `Configs/src` over the installed package.
The environment is reproduced from exact direct and transitive pins with
artifact hashes, and its identity binds both deployed source content and the
lock file. Its runtime-content digest also binds the installed tree and the
bytes behind the fully resolved `bin/python` symlink chain, so a host
interpreter replacement invalidates reuse. Provisioning is explicit, refuses
to replace the environment while either plane is active or its state cannot be
observed, and does not stop, start, or register either plane. After the units
are linked and reloaded, each
process holds shared source-projection and runtime locks for its lifetime;
changed provisioning holds the exclusive runtime lock and checks stopped state
both before building and immediately before swapping the verified environment.
It builds only from a private copy
whose source and lock digests match the initial deployed snapshot, then
rechecks deployed source immediately before publishing the marker and swapping
the environment. Unit link/reload and runtime provisioning are separate
transactions so the loaded units cannot lag behind the locking contract.
Before every managed launch, a read-only unit condition recomputes the deployed
source-and-lock identity and the complete runtime-content digest, including
the resolved interpreter bytes. The final launch path then takes the shared
source-projection and runtime locks, repeats that verification under both
locks, and `exec`s the server without releasing either lock. Source sync,
runtime replacement, and process launch are therefore serialized for the full
service lifetime; source drift or runtime tampering leaves the unit inactive
until explicit stop, sync, and reprovisioning succeed.
Runtime provisioning also establishes two persistent journal files without
truncating existing bytes. Managed units require their existence, give each
process an exact-file write exception under an otherwise read-only system
view, and hide the opposite contour's file. A fixed capacity fails closed;
automatic rollover is deliberately absent until an archive-continuity contract
is reviewed.

`rollback_required` is admissible only for the failed source/package/deploy
links of a rollback plan, and only while the triggering link and its evidence
refs remain unexpired. Other unusable states remain blocked, and usable
freshness plus exact rollback evidence are still mandatory.

Published JSON Schema carries all structurally expressible conditional model
invariants. Runtime Pydantic validation additionally owns cross-field time
ordering, uniqueness, and content-address verification.

## Production observation composition

The live observation is assembled by one stack-owned producer from an explicit
target catalog, the immutable stack deployment receipt, the private `aoa-sdk`
registry projection, named user-systemd fields, and an optional typed evidence
overlay. This is bounded composition, not workspace discovery. The producer
does not read credentials or call owner servers.

The deployment receipt can prove adapter package and deployed bytes. The
private registry can prove only the exact declared registry record. User
systemd can prove the named process state and identity. Every other axis stays
unknown until an issuing owner contributes a typed overlay. In particular, an
owner revision without an owner source-tree digest cannot become an exact
source link, and a listening process cannot become a ready endpoint without an
observed schema.

The committed targets point at the owner-specific read template. Transitional
shared-bearer processes are deliberately outside this observation because the
runtime contract forbids shared credential classes. Migration therefore moves
an observed target from inactive to active; it does not relabel the legacy
process.

## Canary evidence contour

Authenticated canary execution is outside the observation producer and the
agent-facing MCP processes. The operator runner selects one exact committed
target, derives its owner-specific read credential filename from the deployed
service identity, and has no endpoint or tool override. Its schema digest
covers the complete paginated MCP inventory; its result digest covers the
secret-screened structured owner response. Only a reviewed owner-specific
result contract can turn HTTP success into a result-contract match. A separate
source/acceptance-owner grounding review is still required before
`result_grounded` or successful canary evidence exists.

The runner issues stack runtime evidence, not owner freshness or acceptance.
It writes an immutable receipt, a private content-addressed copy of a
successful structured result, and a one-subject overlay whose canary remains
blocked on owner grounding. The result artifact is an untrusted capture for
the owner reviewer, not stack semantic evidence. This leaves aggregation,
central pair-specific proof, consumer registration evidence, owner review,
registry admission, and lifecycle effects as explicit later transactions.
The receipt and result artifact are independently attested by a stack canary
Ed25519 key. Owner reviewers authenticate the issuer only against a public key
pinned outside the capture and its caller-controlled paths. Content addressing
alone remains integrity metadata and is never accepted as issuer
authentication. Signer rotation is explicit and must update the downstream
owner trust pin before new captures can be reviewed.
Reviewed contracts cover every declared migration-wave target. Contract
presence proves only that an exact bounded read shape has been selected; an
inactive endpoint, failed call, schema drift, ungrounded result, missing owner
review, or absent central proof remains explicitly unproved.
