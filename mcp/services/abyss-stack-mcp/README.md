# abyss-stack-mcp

`abyss-stack-mcp` is the stack-owned evidence plane for MCP runtime topology.
It answers questions about the chain from reviewed source through package,
deploy, process, endpoint, registry, consumer schema observation, grounded
canary, and rollback readiness.

It is not a gateway, does not proxy owner tools, does not flatten nested state
into `healthy`, and does not own proof, memory, source truth, or owner
acceptance.

## Admission maintenance

Read contours in the committed runtime-target catalog now have two fail-closed
control surfaces below any owner admission decision. Candidate and
internal-effect processes remain outside this admission preflight until they
have contour-specific target and evidence contracts; a read canary never
authorizes either contour:

- `abyss-stack-mcp-preflight` verifies the exact contour registry entry,
  source/package/deployment tree, measured executable target and digest,
  credential identity and permissions, schema set, unit binding, policy,
  validator, observation, dependency, and rollback routes before launch;
- `abyss-stack-mcp-admission-automation` derives an evidence-bound runtime
  overlay, managed topology and catalog, runs the complete sweep, builds
  per-contour Keeper specs, and asks the exact compatible `aoa-sdk` Keeper to
  publish a private CAS state projection. An optional contour-scoped private
  inbox imports independently issued immutable owner nodes; repeated cycles
  import each node once, reuse only still-compatible nodes, and report both
  avoided refresh cost and the exact invalidated stages. The managed keeper
  consumes the provisioned mode-`0700`
  `${AOA_STACK_ROOT}/Logs/mcp/admission/keeper-inbox` root, shaped as
  `(organ_id)/(contour_id)/*.json`;
- `abyss-stack-mcp-admission-revision` composes one non-publishing registry-v2
  contour revision only after exact current and last-known-good observations,
  central proof, KAG owner acceptance, consumer compatibility, rollback
  readiness, and a separately issued operator decision all bind the same
  shadow predecessor;
- `abyss-stack-mcp-system-status` combines that private projection with the
  managed catalog, owner registry, protocol-lab verdict, and aggregate SDK
  TaskStore state into one private, content-addressed read model.

Path events are primary and a five-minute timer is the backstop. Neither
surface starts or restarts a service, edits the owner registry, extends a TTL,
or issues proof or acceptance. The unified status keeps runtime liveness,
preflight parity, admission currentness, last-good state, blockers, and next
safe steps separate. It also reports protocol pair, credential-generation
observation state, schema digest, owner watermark, refresh transaction/cost,
task quotas, pending cancellation and bounded orphan candidates. Missing live,
credential-generation, or owner-watermark evidence stays `unobserved`. An
active endpoint whose owner registry has expired is therefore reported as live
but blocked, never current; a completed Task likewise never becomes admission.

The current evidence-shaped run covers nine read contours and correctly
reports all nine blocked on the expired registry snapshot, with runtime
liveness unobserved, zero current admissions, one completed owner pilot Task,
and production Tasks disabled. That is an operationally useful mixed status,
not a failed attempt to manufacture a green aggregate.

The generated `organ-contour-supplement.v1.json` adds stack candidate and
internal-effect contours only as shadow shapes. Read admission never transfers
to them. Deployment of the Keeper additionally requires an exact trusted SDK
artifact; an ambient checkout or editable import is not dependency evidence.

For the exact boundary between stack runtime receipts and the source-owned
Codex organ-fabric projection, read
[`docs/CODEX_CONSUMER_HANDOFF.md`](docs/CODEX_CONSUMER_HANDOFF.md). Service
presence cannot register, reload, or remove a Codex consumer.

## Process contours

The owner-authored capability identities are intentionally narrower than a
runtime admission claim:

- `runtime-topology-read` binds the read contour to
  `stack_runtime_catalog`, `stack_runtime_inspect`, and
  `stack_orchestration_inspect` under credential class `abyss-stack-read`;
- `stack-access-plan` binds the candidate contour to
  `stack_prepare_runtime_plan` under credential class
  `abyss-stack-candidate`;
- `exact-read-restart-pilot` binds the separately admitted internal-effect
  contour to `stack_execute_approved_read_restart_pilot` under credential
  class `abyss-stack-internal-effect`.

The machine-readable owner source is `organ-access.v1.json`; its generated
JSON Schema is `schemas/organ-access.schema.json`. It defines identity and
tool bindings only. It explicitly does not assert registry admission, owner
acceptance, proof completion, consumer registration, or effect activation.

The read process exposes only:

- `stack_runtime_catalog`: compact discovery with zero detail-schema bytes;
- `stack_runtime_inspect`: one exact owner/policy target and one selected
  evidence view;
- `stack_orchestration_inspect`: one bounded private host-persistence record
  for an SDK-validated cross-organ snapshot, without owner payload expansion.

Both read tools are server-filtered to `policy_family=read`; omitting the
catalog filter cannot enumerate candidate or effect subjects, and inspection
rejects every higher-policy contour before loading an observation.

The candidate process exposes only:

- `stack_prepare_runtime_plan`: a content-addressed `sync`, `deploy`,
  `activate`, `restart`, or `rollback` candidate.

The internal-effect process exposes only:

- `stack_execute_approved_read_restart_pilot`: execute one approved exact
  restart of `abyss-stack-mcp-read.service`, run an authenticated canary,
  perform a mandatory second restart as restoration, and run a post-rollback
  canary.

It accepts no unit or command parameter. The request names only an already
staged content-addressed restart candidate, a distinct expiring approval, and
their bound idempotency key and exact internal-effect principal. It rechecks the live observation and exact systemd
process identity before mutation, persists a pre-effect receipt, and emits a
secret-free success, denial, or recovery receipt. The process is isolated from
the candidate audit journal and cross-organ orchestration tree and can write
only its private effect root. A persistent attempt receipt and execution lock
limit starts to one serialized pilot per minute; idempotent success replay does
not repeat either restart. Its source manifest does not itself activate the
effect; live admission and approval remain separate transactions.

The processes use different tools, default ports (`5431`, `5433`, `5439`),
environment variables, systemd credential names, scopes, and client
identities. Read and candidate credentials cannot authenticate to or enumerate
the effect process, and the effect credential cannot select another tool.
All contours publish the `abyss-stack-mcp` application version in
`serverInfo.version`; the pinned SDK version is dependency evidence, not the
server identity.
Every exported primitive also crosses the package-local protocol-independent
policy seam. The seam rechecks the authenticated contour identity and scope,
uses an exact tool/effect allowlist, limits canonical input and output bytes,
in-flight calls, starts per minute, and dispatch time, propagates caller
cancellation, rejects secret-bearing inputs or results, and emits a
secret-free allow/deny/cancel receipt containing digests rather than values.
All returned owner/runtime text is marked `content_trust=untrusted_data` and
`instruction_authority=none`. The candidate primitive remains
`prepare_candidate`; its policy receipt never authorizes a runtime effect.
When `ABYSS_STACK_MCP_AUDIT_JOURNAL_PATH` is set, every receipt is appended
before it enters the bounded in-memory read model to one contour-specific,
mode-`0600`, canonical-JSONL hash chain. Startup replays the complete bounded
chain and fails closed on a partial record, digest or sequence drift, a foreign
owner/policy contour, a symlink, broad file permissions, or external size
change. The public-safe `abyss-stack-mcp-audit` summary exposes counts and
continuity metadata, not request/result values. It proves only local journal
shape and hash-chain continuity; it does not prove caller intent, grounding,
admission, owner acceptance, or a runtime effect.
Provisioning validates the three existing or newly created bearer values
together and fails closed unless they are pairwise distinct. It also atomically publishes
a non-secret digest manifest. Each managed startup receives only its own
bearer plus that manifest, verifies that all three committed digests are
distinct, and binds its loaded bearer to the matching contour digest before
the server can listen. Copying or rotating a credential file without
refreshing a valid separated pair therefore fails closed on the next start.
The lifecycle-owned rotation command changes all three contour values and their
manifest only while all three managed units are observably stopped, never prints a
value, and leaves consumer refresh plus restart to a later canary transaction.

Every candidate remains `execution_authorized=false`, requires separate human
approval before any effect, contains no free-form shell command, expires in at
most ten minutes, and stops on observation drift or precondition mismatch.
Every plan requires usable subject freshness. Activation additionally requires
an active process with an observed process identity, a ready endpoint, a
registered consumer with the exact server schema digest and an overlapping MCP
protocol version, a passed central-proof verdict issued by `proof_owner` and
bound to the current source revision and source-tree digest, package, deployed
revision, tree digest, and content-addressed deployment-manifest digest, schema,
running process identity, consumer, and exact canary route and receipt, named
acceptance-owner evidence bound to the current source revision and package
digest, a grounded canary, and usable
rollback proof. Generic activation or restart of `internal_effect` and
`external_effect` targets remains rejected. The D-0106 pilot is narrower: its
separate process may consume only an exact admitted `read` restart candidate
for `abyss-stack-mcp-read.service`, then enforce its own approval, execution,
canary, and mandatory restoration contract. The central-proof and acceptance receipts plus the selected
compatible consumer's exact
`registration_ref` are embedded in ordered activation steps, preceded by exact
process-identity verification. A shadow registry receives an exact admission
action after those gates; an already admitted registry receives verification.
All receipts are copied into the expiring precondition evidence. Rollback requires
usable registry, selected consumer-registration, canary-route, and rollback
evidence, embeds the selected registration target, and carries every one of
those proofs into the candidate. A ready rollback proof must identify the
complete last-known-good consumer registration, package, deploy revision and
tree, content-addressed deployment-manifest ref and digest, unit, credential
class, executable, process identity, and canary route and receipt. The proof
carries a second typed target that must exactly equal that full restoration
contour before readiness is accepted. Its ordered steps
first deny discovery and activation, restore that runtime floor, restore the
consumer registration, and finally run the proven last-known-good canary
rather than the current deployment's canary. Rollback planning relies on the
usable rollback proof that binds that LKG route and receipt; it neither validates
nor copies the current deployment's canary evidence, which may be failed,
blocked, or expired in the recovery scenario. Restart plans also require and
carry usable current-canary and central-proof evidence, verify that the passed
proof names the exact current source, package, deploy, process, server schema,
compatible consumer registration, canary route, and canary receipt before the
restart snapshot, and reject inactive processes, which must use the full
activation contour instead. The selected consumer registration evidence is
copied and expiry-bounded by the restart candidate. A plan expires at the
earliest of ten minutes, its observation/freshness envelopes, every required
link, and every copied evidence ref; it cannot outlive its proof. Candidate
planning allows at most 30 seconds of positive clock skew and rejects
future-dated observations, required links, evidence refs, freshness, or deploy
timestamps beyond it. Required observations must also fall no later than 30
seconds after their enclosing observation snapshot, so an older snapshot
cannot carry causally newer proof. Activation and rollback causality checks use
only the exact proof-selected or last-known-good consumer; unrelated consumer
observations cannot veto a candidate and are not copied into it. Candidate
result freshness is the worst effective state across subject freshness and
every exact link the plan copies, so a drift-backed plan cannot claim `exact`.
Every usable deploy manifest, registered consumer, passed central proof,
accepted owner decision, successful canary, and ready rollback proof also binds
its named receipt or registration target to one contained `EvidenceRef`; for
proof and acceptance, that same ref must be issued by the declared owner. The
candidate copies and expiry-bounds that exact identity before any step can name
it. A deploy manifest ref is valid only at the stack-owned immutable record path
derived from its `sha256:` manifest digest. Package identity also names the
stack adapter revision from which the artifact was built. That revision must
match the stack deployment revision; it is intentionally distinct from the
owner organ source revision carried by `SourceIdentity` and central proof.
Central proof cannot predate the canary link or evidence refs it names.
Duplicate evidence identities with conflicting `observed_at` values are
rejected before expiry deduplication.
Catalog and inspection apply the same 30-second future-skew bound to the
observation envelope, links, freshness, and nested evidence timestamps, using
the earlier of wall-clock time and the enclosing observation snapshot;
causally future usable evidence is reported as `blocked`, never as current,
before candidate planning is involved.
An expired observation envelope likewise downgrades both result metadata and
the derived catalog/freshness/drift fields to at least `stale_readable`, even
when the enclosed subject freshness expires later.
Inspection also folds the effective state of the selected evidence view into
result freshness metadata and exposes it beside the immutable raw owner state.
`rollback_required` is accepted only while its own link and evidence refs are
unexpired; a bare or expired rollback signal is a controlled precondition
failure.
Every plan also names one exact deployed-tree postcondition. Sync takes that
target from the reviewed source identity, deploy takes it from the exact
package identity, activate and restart preserve the observed deployed tree,
and rollback restores the last-known-good tree. The ordered sync/deploy
comparison step uses this future target rather than the pre-action deployed
digest. Rollback denies discovery for the exact registry ID and registry digest
observed by the candidate, not for a mutable registry name alone.

## Host-visible orchestration

`abyss-stack-mcp-orchestration` is a separate operator process for the explicit
KAG evidence → Memo candidate → Eval request/result → owner decision chain. It
never calls an owner MCP. For `start` and each `advance`, it invokes one exact
operator-supplied `aoa-sdk` CLI command, requires the SDK to validate the
complete chain, issues a content-addressed stack host receipt around the
already-produced owner stage packet, and atomically persists immutable
mode-`0600` snapshots under a mode-`0700` run root.

The stack record binds the SDK snapshot digest, canonical file digest, current
stage, next owner, request expiry, validation result, and latest host receipt.
The read MCP exposes only that bounded record through
`stack_orchestration_inspect`. It rechecks the record and snapshot digests on
every read. The candidate MCP process cannot access the orchestration root.

This is host-visible orchestration persistence, not hidden chaining. The
operator must invoke KAG, Memo, Evals, and the final acceptance owner directly
and supply the resulting typed packet. Stack does not compute proof, write
durable memory, infer acceptance, or authorize execution. A stored terminal
state retains the SDK/owner claim and receipt; persistence alone is not
grounding, benefit, admission, or rollback proof.

## Observation input

Set `ABYSS_STACK_MCP_OBSERVATION_PATH` to one explicit secret-free
`abyss_stack_runtime_observation_v1` file. The default live route is:

```text
/srv/AbyssOS/abyss-stack/Logs/mcp/observations/current.json
```

`abyss-stack-mcp-observe` is the source-owned producer for that file. It reads
only five bounded inputs:

- the content-addressed stack MCP deployment manifest and its immutable record;
- the deny-by-default private `aoa-sdk` registry source;
- the committed `abyss_stack_runtime_targets_v1` catalog;
- exact `systemctl --user show` fields for those named unit targets;
- an optional typed, secret-free evidence overlay.

It does not scan sibling workspaces, read a bearer, call an owner MCP endpoint,
or infer a consumer schema, owner-result freshness, central proof, owner
acceptance, grounded canary, or rollback readiness. Unknown owner source tree
digests use the all-zero structural digest only while their source link remains
explicitly `unknown`; that sentinel is never usable by candidate planning.
Package and deploy identity come only from exact stack deployment receipts.

The default observation purpose accepts only the committed current-canary
route. A rollback candidate must be built from a separate invocation with
`--canary-purpose last-known-good`; that mode expects the purpose-qualified
`.../last-known-good` route and does not relax route matching for either lane.

The catalog names all fifteen current read targets, but it intentionally
observes `aoa-organ-mcp-read@...` rather than the transitional
`aoa-mcp-http@...` processes. The latter share one compatibility bearer and
cannot be represented as owner-isolated contours. Until an owner is migrated,
its new process is therefore reported as exactly inactive instead of laundering
the legacy process into a false owner credential class.

The optional
`${AOA_STACK_ROOT}/Logs/mcp/observations/evidence-overlay.json` is a typed
handoff for independently issued source, endpoint/schema, consumer, freshness,
proof, acceptance, canary, and rollback observations. The producer rejects
unknown targets, expired overlays, future-dated overlays, secrets, and usable
source/endpoint/freshness/canary claims that lack the corresponding issuing
owner. It never edits the overlay. Missing or expired overlay evidence falls
back to explicit unknown states.

`abyss-stack-mcp-overlay-compose` can assemble that single handoff file from
multiple independently issued overlay fragments. It validates and
secret-screens every fragment, intersects their expiry envelopes, sorts exact
organ/policy subjects, and merges only disjoint or canonically identical typed
fields. Competing values for the same field fail closed; the composer never
chooses a winner, upgrades a state, or issues consumer, proof, acceptance,
canary, or rollback evidence.

```bash
abyss-stack-mcp-overlay-compose \
  --input /path/to/consumer.overlay.json \
  --input /path/to/canary.overlay.json \
  --output /srv/AbyssOS/abyss-stack/Logs/mcp/observations/evidence-overlay.json
```

`abyss-stack-mcp-proof-project` is a separate non-verdicting bridge for one
already-issued `aoa-evals` bounded packet review. It rechecks the exact eval
source-file digests, packet digest, live source/package/deploy/process/schema,
grounded canary, and one independently issued compatible consumer
registration before it can emit a `proof` overlay field. In particular, the
packet must assert `consumer_registered`; the more limited live materializer
packet that intentionally leaves that axis absent is rejected. The bridge
copies the unchanged eval report into a private canonical-content-addressed
record and attributes the evidence to `aoa-evals`. It does not issue the
verdict, infer owner acceptance, authorize admission or effects, or prove
rollback.

```bash
abyss-stack-mcp-proof-project \
  --review /path/to/aoa-evals-review.json \
  --packet /path/to/exact-proof-packet.json \
  --observation /path/to/current-runtime-observation.json \
  --eval-root /path/to/aoa-evals/evals/boundary/aoa-organ-access-admission-integrity \
  --record-root /path/to/private/proof-records \
  --output /path/to/private/aoa-kag.read.proof.overlay.json
```

Rollback readiness uses two further non-executing processes. First,
`abyss-stack-mcp-canary --purpose last-known-good` commits a distinct canary
route and private receipt lane. After source-owner grounding is composed into
one temporary observation, `abyss-stack-mcp-rollback-candidate` rederives the
exact package at the immutable deployment revision, compares it byte-for-byte
with the deployed tree, verifies the unit and executable, observes credential
metadata without reading the credential, and binds the exact consumer and LKG
canary. Its content-addressed output keeps execution, admission, and rollback
false.

After the existing `aoa-organ-access-admission-integrity` bundle reviews that
candidate, `abyss-stack-mcp-rollback-project` independently repeats the live
binding against the unchanged observation, deployment record, registry,
consumer, source revision, deployed bytes, executable, credential posture, and
LKG canary. Only then does it emit a temporary `rollback.ready=true` overlay,
with the unchanged eval report copied to a private content-addressed record.
Readiness means one restoration contour is currently reproducible; it is not
rollback execution, post-restore health, admission, or effect authority.

```bash
abyss-stack-mcp-canary --organ aoa-kag --purpose last-known-good \
  --output-root /path/to/private/rollback-canaries
abyss-stack-mcp-rollback-candidate \
  --observation /path/to/lkg-runtime-observation.json \
  --deployment-record /path/to/deployments/records/<digest>.json \
  --consumer-id codex-main \
  --output /path/to/private/rollback.candidate.json
abyss-stack-mcp-rollback-project \
  --review /path/to/aoa-evals-rollback-review.json \
  --candidate /path/to/private/rollback.candidate.json \
  --observation /path/to/lkg-runtime-observation.json \
  --deployment-record /path/to/deployments/records/<digest>.json \
  --eval-root /path/to/exact-eval-bundle \
  --record-root /path/to/private/rollback-proof-records \
  --output /path/to/private/rollback.overlay.json
```

## Authenticated read canary

`abyss-stack-mcp-canary` is a separate credential-bearing operator process.
It is not called by the observation producer or either MCP server plane. For
one exact catalog target it reads only that service's read credential and the
stack canary Ed25519 private key, connects
only to the committed loopback endpoint, observes the complete paginated MCP
Tool/Resource/Resource-Template/Prompt schema inventory, calls one committed
read primitive, and writes a content-addressed mode-`0600` receipt plus a
one-subject typed overlay. A successful call also writes the secret-screened
structured response as a separate content-addressed mode-`0600` result
artifact so the source/acceptance owner can review the exact captured payload.
The receipt and result artifact independently carry an Ed25519 attestation over
their complete content-addressed statement. Their public `signer_id` is the
SHA-256 digest of the raw public key. A downstream owner must verify both
attestations against an independently pinned public key before attributing the
capture to `abyss-stack`; a caller-supplied key is not an authentication root.
The signed body also binds the exact deployment manifest, service, source
revision, package digest, deployed-tree digest, and deployment timestamp. The
observation must occur after that deployment. Runtime-overlay construction and
every production preflight re-authenticate the receipt, recheck its TTL, and
compare those deployment fields against the current manifest; a copied,
expired, predecessor, or post-catalog-tampered receipt cannot authorize start.

The bounded timeout includes a listener-readiness window because a systemd
`Type=simple` process can be active before Uvicorn has bound its socket. The
runner retries only loopback TCP connection refusal during that window. Once
the listener is reachable, authentication, MCP initialization, inventory,
tool execution, schema, and result failures are never retried or laundered
into readiness.

Reviewed contracts cover all declared migration-wave targets. Each contract
binds an exact tool and arguments, owner-specific result schema identity, and
the minimum result anchors needed to distinguish a contract match from a
merely successful HTTP call. The connector contracts assert read-only and
`network_touched=false` boundaries without flattening owner readiness into the
top-level status. Contract presence does not create endpoint readiness,
grounding, freshness, owner acceptance, central proof, rollback proof, or
admission; any missing evidence axis still fails closed.

The receipt records the signer identity, attestation algorithm, attestation,
digests, bounded counts, application-reported server
identity, protocol, latency, reason codes, and the deterministic private
result-artifact ref, never the bearer or inline owner payload. The separate
artifact marks the payload as untrusted data with no instruction authority;
its existence and content address are capture evidence, not owner grounding.
The overlay proves endpoint/schema observation but keeps the canary
blocked pending a separate owner grounding review. It intentionally contains
no Codex registration, owner grounding, owner freshness, central proof, owner
acceptance, admission, or rollback claim. A successful call and result-contract
match therefore remain only inputs to the later pair-specific eval and owner
review.

For a contour with no prior admission, use its manual bootstrap unit only long
enough to issue the first receipt. The bootstrap unit has the exact production
credential, endpoint, sandbox, and `ExecStart`, but no registry/catalog
preflight; it conflicts with production, never restarts, has no `[Install]`
section, and is killed after ten minutes. The complete first-admission sequence
is: verify an exact deployment, start only the matching bootstrap unit, issue a
receipt explicitly bound to that bootstrap process, build the runtime overlay
and managed catalog while that signed process is still active, review the
preflight result, stop bootstrap, then start the normal unit and immediately
issue a second receipt bound to the production PID/start identity.
Only that second receipt can enter final proof, acceptance, rollback, and
admission. Bootstrap is not a general recovery bypass and must never be
enabled.

For example:

```bash
systemctl --user start aoa-organ-mcp-read-bootstrap@aoa-kag.service
abyss-stack-mcp-canary --organ aoa-kag --process-unit bootstrap
systemctl --user start abyss-mcp-admission-keeper.service
# Review Logs/mcp/admission/managed-contours.json and the preflight result.
systemctl --user stop aoa-organ-mcp-read-bootstrap@aoa-kag.service
systemctl --user start aoa-organ-mcp-read@aoa-kag.service
abyss-stack-mcp-canary --organ aoa-kag
# Refresh proof and admission only from this production-process receipt.
```

The stack auth provisioner creates the canary signing key once as a regular
current-user-owned mode-`0600` Ed25519 private key alongside the contour bearer
files and pins its derived mode-`0600` public key for stack-owned admission
verification. Reprovisioning validates and preserves that key pair; bearer rotation does
not silently rotate the capture trust root. Public-key pinning and any later
signer rotation require a separately reviewed consumer-owner update.
The internal-effect unit receives systemd's read-only mode-`0400`
`LoadCredential` projection of that same owner-only key; the canary reader
accepts only those two owner-only modes and still rejects group/world access.

The command never starts or stops a unit, changes consumer configuration,
merges the overlay into the production observation, invokes the owner
reviewer, or admits the registry entry.

Production refresh uses `abyss-stack-mcp-observation.service` and its two-minute
timer. Runtime provisioning creates the private mode-`0700` observation
directory but neither starts nor enables the producer. Run the oneshot once
before starting a stack MCP plane; enable the timer only as an explicit
rollout action. Both stack MCP planes have a `ConditionPathExists` guard for
the produced file.

The loader rejects symlinks, non-files, payloads above 2 MiB, unknown contract
fields, secret-like keys or values, shared credential classes, non-loopback
HTTP endpoints, credentials embedded in URI userinfo/path/query/fragment references,
encoded nested credential references, unparseable or excessively nested
URI-like references, whitespace-only exact targets, and unsupported effect
classes. Credential-key screening includes passphrases and recognizes
namespaced separator and camel-case token sequences rather than only exact key
spellings. Unambiguous credential components such as `secret_access_key` are
rejected even without a provider namespace, including AWS-style
`aws_secret_access_key`. Exact `credential` and `credentials` keys are also
rejected without treating the typed `credential_class` identity field as
secret material. AWS presigned-query keys `X-Amz-Credential`,
`X-Amz-Signature`, and `X-Amz-Security-Token` are rejected as bounded
credential material. Concatenated
matches require a recognized provider/consumer namespace or credential-value
attribute boundary, so ordinary keys such as `tokenizer`, `passwordless`, and
`authorizationPolicy` remain valid.
Basic/Bearer prefix checks ignore leading whitespace. Bounded provider-token
patterns are scanned throughout direct and decoded reference values, covering
the standard OpenAI, GitHub, and GitLab token families, including GitLab
personal, deploy, runner, job, trigger, agent, workspace, SCIM, and feature-flag
client tokens. Expired observations remain visible as stale read evidence but
cannot produce a candidate plan.
The generated Draft 2020-12 schema includes the conditional invariants for
usable links and freshness, endpoint readiness, consumer registration,
active-process identity, accepted-target completeness, successful canaries,
central-proof target completeness, rollback readiness, and policy/effect
pairing. The Pydantic loader remains the final authority for loopback endpoint
parsing, relative clock-skew, relational timestamp, proof/acceptance-owner
provenance, target and proof-before-acceptance ordering, uniqueness, and
content-address checks that JSON Schema cannot express.

The committed example is fictional and public-safe. It is neither a live
runtime capture nor admission evidence.

## Portable use

```bash
python -m pip install -e mcp/services/abyss-stack-mcp
abyss-stack-mcp-observe \
  --deployment-manifest /path/to/deployments/latest.json \
  --registry /path/to/organ-registry.source.json \
  --output /path/to/observations/current.json
abyss-stack-mcp-observe \
  --deployment-manifest /path/to/deployments/latest.json \
  --registry /path/to/organ-registry.source.json \
  --overlay /path/to/lkg.overlay.json \
  --canary-purpose last-known-good \
  --output /path/to/observations/lkg.json
abyss-stack-mcp-overlay-compose \
  --input /path/to/consumer.overlay.json \
  --input /path/to/canary.overlay.json \
  --output /path/to/observations/evidence-overlay.json
abyss-stack-mcp-proof-project \
  --review /path/to/aoa-evals-review.json \
  --packet /path/to/exact-proof-packet.json \
  --observation /path/to/current-runtime-observation.json \
  --eval-root /path/to/exact-eval-bundle \
  --record-root /path/to/private/proof-records \
  --output /path/to/proof.overlay.json
abyss-stack-mcp-canary --organ aoa-kag --purpose last-known-good \
  --secret-dir /path/to/private/secrets \
  --output-root /path/to/private/rollback-canaries
abyss-stack-mcp-rollback-candidate \
  --observation /path/to/lkg-observation.json \
  --deployment-record /path/to/deployments/records/<digest>.json \
  --registry /path/to/private/organ-registry.source.json \
  --consumer-id codex-main \
  --output /path/to/rollback.candidate.json
abyss-stack-mcp-rollback-project \
  --review /path/to/rollback-review.json \
  --candidate /path/to/rollback.candidate.json \
  --observation /path/to/lkg-observation.json \
  --deployment-record /path/to/deployments/records/<digest>.json \
  --eval-root /path/to/exact-eval-bundle \
  --record-root /path/to/rollback-proof-records \
  --output /path/to/rollback.overlay.json
abyss-stack-mcp-canary --organ aoa-kag \
  --secret-dir /path/to/private/secrets \
  --output-root /path/to/private/canaries
abyss-stack-mcp --observation-path /path/to/observation.json catalog
abyss-stack-mcp --observation-path /path/to/observation.json \
  inspect aoa-kag read --view proof
ABYSS_STACK_MCP_POLICY_FAMILY=read abyss-stack-mcp-server
abyss-stack-mcp-audit --journal /absolute/policy-read.jsonl \
  --policy-family read
```

Stdio is the portable default. Authenticated loopback Streamable HTTP is
selected through `AOA_MCP_TRANSPORT=streamable-http`; it requires the
plane-specific credential. Portable `catalog` and `inspect` are read-contour
commands; `plan` requires explicit `--policy-family candidate`.

The managed user units do not use ambient Python. After syncing the package to
`Configs`, first link and reload the lock-aware units, then provision the
source-addressed runtime explicitly:

```bash
scripts/aoa-install-systemd --all-user-units
scripts/aoa-install-systemd --provision-abyss-stack-mcp-runtime
```

These are intentionally separate transactions; combining both flags is
rejected so provisioning cannot run before the link-and-reload phase. The
standalone provision step verifies that all three units are loaded from the
expected managed fragments and that user systemd's effective `ExecStart`
contains the exact shared runtime lock; absent, stale, or unexpectedly sourced
unit definitions fail closed and require another `daemon-reload`.
This creates or refreshes
`${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv`, installs the exact
`requirements.lock` closure with `--require-hashes`, verifies its dependencies,
and records a runtime identity composed from both the deployed-package digest
and the lock digest, plus a deterministic content digest of the installed
runtime files, symlink targets, and bytes of the fully resolved
`bin/python` interpreter. Before that digest is recorded, generated entry-point
shebangs are rebound from the private staging directory to the stable published
venv path, so atomic publication does not leave launchers pointing at a removed
directory. Repeating the command with unchanged source and lock rehashes the
installed environment before verification and reuses it only when the content
digest still matches; missing or changed installed or interpreter bytes force a
guarded rebuild. A changed identity is never installed
over a running plane: provisioning fails closed while any read, candidate, or
internal-effect unit is active or its user-systemd state cannot be observed.
Stop all three units explicitly before reprovisioning, then start or canary them as a
separate action. The units have `ConditionPathExists` guards for the runtime
and both lock files, an executable `ExecCondition`, and a read-only verifier
condition. Their final launch path then acquires the shared source-projection
lock followed by the shared runtime lock, repeats the complete deployed
source-and-lock plus runtime-content verification under those locks, and only
then `exec`s the server. They remain inactive when the runtime is absent,
unusable, drifted, or no longer matches the deployed package. Both shared locks
remain held for the full process lifetime. Changed provisioning and applying
MCP Configs sync therefore fail closed while any plane runs; stop all three
planes explicitly before either operation. Provisioning checks all unit
states before the build and again immediately before the guarded environment
swap, and aborts if a start races the build. Linking and reloading the
committed units before provisioning is therefore a required rollout
precondition.
The provisioner copies the deployed package into a private staged snapshot,
requires that snapshot and its lock to match the initial digests, installs only
from the snapshot, and rechecks the deployed tree before writing the runtime
identity or swapping the environment. It also holds the same exclusive
source-projection lock that an applying MCP Configs sync holds for its complete
rsync transaction. A sync and provision transaction therefore cannot cross
each other's publication boundary or publish mixed or mislabelled runtime
bytes.
Every provisioner Python call clears inherited `PYTHONHOME`/`PYTHONPATH` and
uses isolated interpreter mode, including venv creation, pip installation,
dependency checks, and import verification.
They execute the package installed inside that venv, not `Configs/src`.
All three units clear ambient `PYTHONHOME`/`PYTHONPATH`, invoke the venv with Python
isolated mode, and pass `-B` explicitly so service imports cannot add bytecode
to the measured environment. A user-manager import override therefore cannot
precede the measured site-packages, and a normal launch cannot invalidate the
recorded runtime-content digest.
Consequently, a later Configs sync cannot cross a running plane or mix new code
with an older dependency closure; after explicitly stopping all three planes, the
synced package becomes eligible for a later start only after this explicit
reprovision step succeeds.
The same explicit provision action creates, but never truncates, the
contour-specific audit journals at
`${AOA_STACK_ROOT}/Logs/mcp/audit/policy-read.jsonl` and
`policy-candidate.jsonl`. The directory is mode `0700`, each file is mode
`0600`, and the read-only runtime verifier requires both safe paths. Each unit
can write only its own journal under `ProtectSystem=strict` and makes the other
contour's journal inaccessible. Managed startup requires the configured
journal and validates its complete chain before listening.
Provisioning also creates the mode-`0700`
`${AOA_STACK_ROOT}/Logs/mcp/observations` root without creating or rewriting
evidence. The producer receives that directory as its only writable stack path
and atomically publishes mode-`0600` `current.json`.
It also creates the non-symlink mode-`0700`
`${AOA_STACK_ROOT}/Logs/mcp/admission/keeper-inbox` root. Provisioning writes no
owner evidence into it; independent owners stage immutable evidence nodes in
the matching contour directory and the Keeper validates every node before
import.
Provisioning creates a separate mode-`0700`
`${AOA_STACK_ROOT}/Logs/mcp/internal-effects/read-restart-pilot` root for the
effect process. It does not stage a plan, issue approval, start a unit, or
authorize an effect.

Runtime dependencies and the build backend are exact pins in
`requirements.constraints`; the one direct artifact requirement is the immutable
`aoa-sdk v0.10.2` GitHub Release wheel. The committed `requirements.lock` binds
that public release to SHA-256
`cf512a7b0a00f8707e21b3950b147d01b7fd2317d64ce7fbcba004a2d1846e2f`
and carries hashes for the entire resolved closure. The validator rejects any
other SDK URL or digest. Regenerate the lock from the repository root with
`pip-tools==7.6.0`:

```bash
pip-compile --generate-hashes --resolver=backtracking --strip-extras \
  --all-build-deps --allow-unsafe \
  --constraint mcp/services/abyss-stack-mcp/requirements.constraints \
  --output-file mcp/services/abyss-stack-mcp/requirements.lock \
  mcp/services/abyss-stack-mcp/pyproject.toml
```

The managed journal limit is 32 MiB per contour. Capacity exhaustion rejects
the next policy decision instead of dropping or overwriting evidence.
Automatic rotation is intentionally not admitted yet: stop the affected plane
and use a reviewed archival/continuity handoff before replacing a journal. Do
not rotate, truncate, or edit it while the plane is active.

## Validation

Run the commands in [AGENTS.md](AGENTS.md).
