# Changelog

All notable changes to `abyss-stack` will be documented in this file.

The format is intentionally simple and human-first.
Tracking starts with the community-docs baseline for this repository.

## [Unreleased]

### Fixed

- Canonicalize external Codex actor baseline diffs with full Git object IDs
  on both the admitted source manifest and private actor projection, so a
  real workspace-write launch cannot fail on equivalent abbreviated index
  lines.
- Keep `.agents/skills` portable for external Codex actor workspaces by
  representing absent host-only owner links as checkout-safe pointer files.
  The source workspace manifest and runtime-owned actor projection now retain
  the required surface without copying the canonical `aoa-skills` content.
- Let a fixed landing-track study packet explicitly carry the runtime's
  `indirect_command_policy` into each bounded writer task. The default remains
  fail-closed; a packet may opt into `sandbox_confined` only when the exact
  runtime binding proves the matching workspace sandbox, disabled network, and
  absence of secret or external-effect authority.
- Normalize that packet policy in the writer-preparation path before emitting
  `task.json`, so both the fail-closed default and an explicit
  `sandbox_confined` selection remain executable.
- Add the explicit `landing-workspace-write-preview-v1` profile for bounded
  change plans where one coder incarnation owns both the read-only preview and
  the repo-mutation step; the task effect ceiling remains `repo_mutation`.
- Close the external Codex workspace-hygiene boundary: admission preflight now
  uses a stable environment without creating or receiving an attempt-local
  Python cache prefix through `state_root`, while every real start/resume
  attempt remains distinct and scratch-bound across admitted workspace-write
  profiles. Actor-safe UTF-8 redaction now maps literal, Unicode-escaped,
  slash-escaped, mixed, and nested source aliases back to exact source spans,
  preserving unrelated backslash/newline/slash bytes instead of decoding an
  entire evidence text layer. Focused regressions cover the exact validation
  argv boundary and both invariants.
- Route Python bytecode and pytest cache output for every external Codex profile
  through a runtime-generated prefix beneath the current attempt's scratch
  directory, outside the actor projection. The invariant covers generic
  structured owner-duty writers and landing writers, including explicit
  `py_compile` and ordinary imports, while preserving exact owner-signed
  validation argv and `validation_command_id` receipts. Resumed attempts use
  distinct scratch coordinates and leave no Python or pytest residue in the
  actor final manifest.
- Qualify nested external-Codex validation evidence by the producer result's
  exact terminal model-report attempt, requiring its number to equal
  result.attempt_count, record that attempt identity in the namespace, and fail
  closed on absent, mismatched, or duplicate successful observations within
  that attempt. Reordered observations from resumed attempts no longer select
  a receipt by array position or global uniqueness.
- Return an admitted external actor's stable `aoa-agents` owner-request
  identity in `owner_admission_ref` while retaining the runtime-private
  immutable request snapshot as separate path-addressable evidence. This lets
  downstream summon closeout match the exact selected request without
  weakening byte-drift detection. Terminal recovery, ordinary result reads,
  and continuation admission now rebind both identities to durable state, so
  a schema-valid semantic substitution cannot ride an intact evidence snapshot.
  Review-seed issuance, reviewer preparation, and initial parent re-entry child
  admission enforce the same binding before consuming a terminal result.
  New receipts use runtime state v4 for this representation. Existing v3
  receipts remain readable, reviewable, resumable, and re-enterable only with
  their exact historical path-shaped owner reference and immutable digest;
  the two representations cannot be interchanged within one state version.
  A non-replacing owner-generation anchor now binds this distinction outside
  the rewriteable session directory. Deleting its same-UID pathname fails
  closed and cannot reopen legacy migration: only exact pre-upgrade sessions
  listed in a catalog sealed into the verified content-addressed release may
  use the explicit digest-pinned migration operation. The authored catalog is
  empty; an operator inventory may be packaged only while staging that release,
  and the release cannot be published by ordinary install or activation. Only
  host-gated `activate-admitted` may activate the catalog after artifact trust
  binds the complete release manifest. Normal reads cannot create a migration
  record. If the controller crashes after publishing a new current-generation
  anchor but before its first state, an exact retry reuses the anchor timestamp,
  verifies and reuses the matching unpublished actor projection, reconciles an
  already-durable prepared event when present, and completes the same admission
  instead of conflicting with itself.
- Pin both external Codex specialized-environment profiles to the landed
  `aoa-stats` actor-responsibility receipt revision, so a release built from
  the current validation dependency can package and verify that same owner
  source instead of retaining the pre-admission snapshot.
- Shorten external Codex admission without caching or dropping proof: the
  independent version, login, model-catalog, subreaper, and nested-sandbox
  probes now overlap in bounded process-isolated groups with exact timeout and
  descendant cleanup. The deterministic suite keeps real transport,
  credential, containment, and full-lifecycle sentinels while unrelated
  lifecycle/authority cases use a fork-inherited fixture-only successful
  preflight double, preserving production admission and worker revalidation.
  Agent OS and governed review-packet semantic tests now inject their bounded
  advisory trace instead of silently calling a deployed endpoint and waiting
  through its timeout fallback; explicit live evidence remains separate.
- Require every external owner-contour request to repeat the exact SDK run-plan
  and model-realization identities from its evidence-complete incarnation
  binding. Preflight now rejects a caller that substitutes either explicit ref
  and recomputes only the request digest.
- Admit a created or deleted structural parent directory in an external
  actor's final workspace delta only when the same exact delta contains a
  strict descendant whose own change is already authorized. Normal closeout,
  failure closeout, and failed-writer recovery now share this complete-delta
  rule, while empty parents, siblings, symlinks, type changes, invalid paths,
  and unrelated descendants remain authority-blocked with their precise
  observation codes preserved.
- Shorten the modern MCP cold-start admission transaction by collecting
  independent organ canary pairs through a bounded three-worker pool. Each
  organ still records last-known-good before current, both full 11-organ waves
  still join before publication, invalid worker counts fail closed, and one
  worker restores exact sequential scheduling.
- Preserve an external actor's exact role, Codex thread, task, projection, and
  authority across a pre-turn ChatGPT usage-limit failure. The explicit
  `capacity_recovery` route requires the exact prior result digest, a
  result-bound structured provider error/`turn.failed` pair, zero observed
  work or effects, and unchanged source/projection evidence; generic process
  failures remain terminal.
- Treat zsh inline execution as opaque because it reads the host-global
  `zshenv`, and reject `find` file-output actions aimed at private Git metadata
  while preserving ordinary Bash inline work and ordinary find reports.
- Mark login, interactive, rcfile, and init-file shell modes as opaque startup
  dispatch while continuing to inspect their inline body for forbidden effects.
- Parse direct and option-attached argv coordinates before secret-effect
  classification, so `diff`, `grep`, `sed`, `wc`, `sort`, and equivalent
  system-utility forms cannot conceal a credential or private Git-config read.
- Embed each installed wrapper's Python bootstrap and exact `active.json`
  digest in its already-admitted static ELF, so a same-UID replacement of an
  adjacent companion or active-record bytes cannot execute host code before
  release verification and containment.
- Reject ignored conventional credential files such as `.npmrc` before their
  bytes are hashed into an actor projection, and classify direct model reads of
  those coordinates as secret access.
- Disable promisor lazy fetches in the projection-local Git environment, so
  private-Git packing cannot invoke a source checkout's configured remote
  helper before the actor containment boundary.
- Remove the last role-scoped MCP bearer from the external runtime's
  exec-time environment: the installed CLI now re-execs through a clean
  environment and carries exact bearer bytes in a bounded sealed descriptor,
  while actor permissions deny `/proc`. Parent yield/re-entry turns receive an
  isolated non-writable `HOME` and have tool-bearing features disabled before
  inference. Prepared non-landing independent reviewers may now consume their
  exact writer projection under the derived review family, and A2A publication
  revalidates the canonical writer `result.json` in its final locked snapshot.
- Propagate only a profile's validated, verified-release-bound specialized
  environment into model-issued shell commands through an explicit Codex
  `shell_environment_policy.set` map. Landing actors can now execute their
  pinned pytest, packaged `aoa_sdk`, and `aoa-stats` validation tools without
  leaving pytest cache residue, while generic profiles retain the core-only,
  secret-filtered shell environment. Public artifact sanitization now gives an
  isolated home nested below host temp the stricter home-redaction treatment.
- Bind every canonical independent reviewer to its exact capability across the
  SDK summon request, scenario, and active review step. A selected
  specialization resolves its owner-authored capability pack; an existing
  base-role reviewer continuum retains only the unique capability already
  named by its canonical request and admitted scenario. Preflight now rejects
  a writer or reviewer whose non-empty summon capabilities are absent from the
  run plan, or whose summon role, incarnation, parent task, session, outputs,
  transport, review posture, or workspace semantics differ from the exact
  launch and task, instead of allowing a real session that can never pass A2A
  closeout.
- Resolve symbolic `runtime:workspace-final-manifest#...` evidence anchors as
  exact top-level JSON members. A shorter token such as `git_head` can no
  longer pass by occurring inside the real `source_git_head` member name;
  bounded line anchors and exact members such as `content_entries` remain
  valid.
- Carry the existing `sandbox_confined` indirect-command policy into every
  canonically prepared read-only landing reviewer. Composite local inspection
  commands remain admitted only under the exact read-only, approval-never,
  network-disabled, secret-free, external-effect-free incarnation posture;
  wider postures, known forbidden command families, and abnormal worker-death
  closeout still fail closed.
- Bind a fixed validation return either to one unchanged final actor manifest
  at every command receipt or to the exact complete terminal validation suffix
  whose last receipt binds the final manifest. This preserves refusal of later
  model commands and post-validation workspace drift while tolerating
  controller-visible transient command-sandbox cleanup between exact
  owner-fixed validation commands.
- Preserve a bounded repo-mutation actor's exact role and Codex thread when an
  otherwise authority-safe terminal return fails only model-report admission.
  The same-role `bounded_repair` route requires the exact prior result digest,
  unchanged owner source, durable actor final-manifest and delta evidence, and
  every observed change to remain inside the original allowed paths; it keeps
  the original authority envelope and preserves the failed result closure.
- Retry only transient regular-file identity/read and disappearing-directory
  enumeration races while taking an actor manifest, rebuild the whole manifest
  on each bounded attempt, retain
  immediate fail-closed handling for every other projection error, and keep
  the original runtime observation error text in durable failure evidence.
- Bind the external Codex runtime to the exact model-organ write-profile IDs
  used by landing and structured owner-duty Luna realizations, while keeping
  both aliases model-neutral, projection-isolated, network-disabled,
  external-effect-free, and observe-only in usage accounting.
- Harden the external Codex contour against hidden pre-execution and
  observation escape seams: opaque `git ls-remote` transport-helper dispatch now fails
  closed; ripgrep preprocessor, hostname-helper, and decompressor modes are
  opaque while ordinary searches remain admitted and ambient ripgrep config is
  disabled; GNU sort compression helpers and hidden Git ref mutations now fail
  closed while ordinary sorting and ref inspection remain admitted; all
  model-issued Git config access now fails closed so credential-bearing reads
  cannot reach the model, and Git remote access is limited to name listing so
  credential-bearing URLs stay opaque; jq environment reads are classified as
  secret access; accepted abbreviated Git filter-program options, Bash
  startup-file options, and Git metadata/object mutations invisible to the
  workspace manifest now fail closed while
  read-only metadata inspection remains admitted; each
  installed launcher is a static x86_64 ELF that removes
  ambient `LD_*` injection before its first dynamic exec; and verified release
  bytes are mounted at a namespace-private read-only `/mnt` coordinate rather
  than overlaying a host-visible release path that could be renamed or
  replaced. The external actor's Git-config mask now reconstructs affected
  metadata parents inside namespace-private `tmpfs` views, so reserving absent
  config and lock coordinates cannot create host files. Jq and GNU-abbreviated
  pattern and pattern-file operands plus attached generic-mutator destinations
  can no longer hide Git-config reads or metadata writes. Owner and masked
  status comparison now fixes rename display explicitly, so harmless local
  `status.renames` preferences cannot reject a valid repository. The mount gate now uses a
  bubblewrap-retained socket peer,
  so supervisor EOF cannot release a rejected launch; abort still kills and
  reaps the gated wrapper before closing the supervisor endpoint. The exact
  mount-wrapper digest proven by nested-sandbox preflight is retained through
  inference launch, so a replacement between those phases fails closed, while
  older durable v2 states remain readable for observation and result recovery.
  The actor now materializes a runtime-owned projection through open source
  descriptors and constructs a source-independent private `.git` body whose
  status/diff match the admitted baseline. Source manifests are recorded before
  and after materialization, and source-byte, parent-identity, orphan-staging,
  publication ABA, or post-open projection-path races fail closed. Projection
  publication is pinned to a parent descriptor and its baseline to the retained
  staging inode; non-replacing publication records rename commitment before
  verification and cleans only that inode after failure. Actor-facing immutable
  inputs are schema-validated derivatives that structurally remove
  source/ancestor coordinates from keys and values, reject collisions, and
  normalize bounded nested Unicode/string escapes—including mixed text,
  slash/hex-case variants, surrogate pairs, and invalid-UTF-8 binary shadows—
  across arbitrary text and model-facing control views; controller
  originals stay denied. Actor baseline/final manifests
  and a canonical before/after delta are durable;
  create/modify/delete/binary/mode/symlink changes stay in the projection and
  the source checkout remains unchanged. Reviewer launches reuse an exact
  controller-issued writer projection envelope and bind terminal result,
  actor-manifest/delta, source-manifest, parent task, and reviewer evidence.
  Reviewer preparation/execution no longer needs the historical source checkout.
  Reviewed A2A export now binds `landing_review` at admission and final export,
  and revalidates that exact seed, all exported writer/reviewer artifacts, and
  both summon request/schema pairs under the writer/reviewer locks. Worker-death
  closeout promotes observed read-only, source, or out-of-scope drift to
  `authority_blocked`.
  Inference mounts the exact open actor inode at a stable child coordinate and
  finalization rejects pathname/inode replacement. Result v2 requires successful
  projection provenance while legacy result v1 and state v1/v2 remain readable;
  old state cannot start inference without a safe v3 projection.
- Make the Codex MCP cold-start barrier observable instead of presenting a
  blank terminal during the several-minute admission transaction. The launcher
  now reports recovery immediately, prints bounded unit/listener progress every
  fifteen seconds, and announces the final readiness handoff without weakening
  the existing 11-of-11 requirement or ten-minute fail-closed timeout.
- Close the modern MCP boot race seen by new Codex sessions. The recovery
  timer now starts after one second, the source-owned Codex credential launcher
  synchronously requires all eleven production units and loopback listeners
  before `exec`, and an incomplete production fleet reuses still-current
  admission only when its deployment, production canaries, and managed catalog
  match exactly. A time-current predecessor deployment now takes the bounded
  bootstrap handoff instead of repeatedly replaying a fail-closed production
  preflight; reusable admission still restarts production without resetting
  claims. Admission Keeper and preflight sweep now settle finite publication
  bursts behind that recovery transaction without becoming permanently failed
  through `unit-start-limit-hit`.
- Recover the exact modern MCP read fleet after a cold start outlives registry
  or contour currentness. The admission backstop now resets only an expired
  registry to claim-free shadow state, uses the existing manual bootstrap
  units to rebuild an 11-of-11 preflight catalog, then requires a complete
  production handoff and production PID/start canary family before publishing
  final admission and rebuilding the managed catalog. Candidate and effect
  contours remain untouched, bootstrap units remain unenabled, and every
  partial recovery stops bootstrap plus any controller-started production
  handoff before failing closed.
- Allow the admission composer to renew an already-admitted contour only after
  its currentness window has expired according to the normalized composition
  clock. The refresh remains bound to the exact predecessor digest and the
  complete current owner/runtime/consumer/proof/acceptance/rollback evidence;
  a still-current contour and a merely future-dated operator decision both
  fail closed. The managed stack runtime now pins the public `aoa-sdk 0.10.2`
  release wheel and its exact SHA-256 so this refresh contract is present in
  the production dependency closure.
- Bind registry-v2 runtime overlays to the live named user-systemd process
  identity and the immutable deployment record instead of treating MCP
  `serverInfo` and mutable `latest.json` as process and deployment identities.
  An inactive or unobserved managed process now fails the projection closed,
  while one expired or invalid sibling canary blocks only its own contour
  instead of aborting the complete managed refresh. Admission now also keeps
  the live LKG PID observation distinct from the rollback target's verified
  stable executable identity, rehashes that executable before admission, and
  signs the exact named-systemd PID/start identity after proving that it stayed
  unchanged across the canary probe. Runtime projection requires that signed
  identity to equal the current process and validates the complete
  content-addressed deployment record, and a malformed sibling receipt is now
  a contour-local skip rather than a sweep-wide parse failure. Managed organ
  units retain the exact opened launcher inode for their complete lifetime, so
  admission hashes process-backed launch bytes rather than a replaceable
  pathname. Admission re-observes the exact systemd PID/start identity before
  and after hashing, avoiding any comparison between systemd monotonic time
  and the different `/proc` boot-time clock. First admission now records the
  bounded organ or stack-owned bootstrap process explicitly, materializes the
  transitional catalog while that process remains live, and
  requires a second production-process receipt before final proof or
  admission, avoiding a preflight/canary startup cycle without weakening the
  final identity gate.
- Move the observation producer onto registry v2 and bind the managed
  admission Keeper to its provisioned private owner-evidence inbox, so the
  production units exercise the same v2 and incremental-refresh paths proven
  by the package instead of leaving them CLI-only.
- Align the `aoa-session-memory` runtime canary with its landed bounded
  `session-evidence-read` HTTP profile by probing the admitted literal-route
  planner instead of the deliberately hidden full-surface status tool.

### Added

- Reranker owner memory relief now uses a separate
  `AOA_RERANK_EXIT_AFTER_MEMORY_RELIEF` switch, atomically drains new requests
  before a clean container restart, and commits one of up to 32 action-ID
  receipts under `Logs/rerank-api` before releasing the model so retries remain
  idempotent across that restart.
- `abyss-stack-mcp` 0.5.2 now consumes registry v2 observations and can compose
  one content-addressed KAG read-contour admission revision from exact current
  runtime, consumer, central-proof, owner-acceptance, freshness, rollback,
  last-known-good, and separately issued operator evidence. It cannot publish
  the registry, authorize an effect, or issue any stronger-owner receipt.
- Registry-v2 rollback candidate generation now binds the exact read-contour
  digest and contour credential contract instead of requiring a v1 organ-level
  record, while observation output selects that same contour identity and
  preserves absent contours as absent.
- Admission automation can import contour-scoped immutable owner evidence from
  a private non-symlink inbox, deduplicates it by content address, and reports
  imported nodes plus avoided full-refresh cost so unchanged renewal benefit
  is directly measurable without executing owner tools.
- Decision `ABYSS-STACK-D-0106` and a third, separately credentialed
  `abyss-stack-mcp` process admit one exact internal-effect pilot on loopback
  port `5439`. Its only tool consumes a content-addressed read-service restart
  candidate and expiring human approval, rechecks live source/package/deploy
  and process identity, writes pre-effect or denial evidence, performs an
  authenticated canary, mandates a second exact restart as restoration, and
  proves the post-rollback state. The process has no generic unit, command,
  source-mutation, lasting applied-state, or external-effect route.

- The MCP protocol lab now separates the observed production
  Codex/Abyss `2025-11-25` wire from the `2025-06-18` fallback of one isolated
  Codex-to-Python-MCP-2 probe. It also records Python MCP `1.29.0` as the
  current maintenance release and distinguishes the latest public conformance
  release (`v0.1.16`) from the exact tested `0.2.0-alpha.10` next-wire package;
  migration to `2026-07-28` remains fail-closed.

- A source-local external Codex incarnation runtime now admits a task-family-
  neutral owner contour: exact `aoa-agents` obligation, mandate, accepted
  responsibility transfer, domain procedure, and ready `aoa-skills` task-local
  DAG precede the `aoa-models` realization and `aoa-sdk` post-compile binding.
  A model-neutral non-starting binder creates the exact separate OS-process
  launch without using built-in Codex subagents; the semantic execution request
  remains a separate owner artifact. Eval, stats, memo, and landing can use
  exact role-scoped profiles, including one named loopback AoA MCP whose token
  is withheld from the model shell. Transport fixtures remain bounded
  compatibility evidence. Exact byte manifests include ignored
  workspace content while refusing secret-shaped ignored inputs, validation
  claims bind to observed argv/exit states, required review cannot close as
  completed, produced-artifact and status-selected wake claims fail closed,
  high-risk command families and path drift remain bounded, and Linux
  parent-death/subreaper containment covers TERM-resistant `setsid` descendants
  and unexpected worker death without pre-empting Codex's own sandbox
  namespaces. A2A return remains gated on a
  different accepted reviewer runtime and thread;
  usage is observe-only rather than an execution budget, stable
  immutable/source/runtime-validation evidence schemes fail closed, admission-
  time failure closeout survives later input drift, and canonical reviewer
  preparation forwards exact writer evidence into a distinct non-started
  session. Mutation paths, source-evidence paths, and the controller-owned
  post-exit manifest identity are separate. A session-local output schema pins
  exact task/incarnation IDs. Same-thread continuation evidence is now carried
  as exact inline UTF-8 bytes with full provenance, prevalidated as one set,
  preserved under controller authority, projected through an actor-safe
  immutable envelope, and admitted into only the session-local evidence schema;
  the runtime never follows an evidence path supplied by the actor or caller.
  One explicit prior-result-digest-bound route
  can continue the same unchanged read-only reviewer thread after an identity
  typo while preserving the failed receipt. Every admitted resume now
  preserves its prior terminal receipt, and an interruption before Codex emits
  turn usage is reported as partial observation rather than zero work. A
  semantically read-only launch now gives Codex a distinct attempt-local
  execution root and `TMPDIR`; the target checkout stays outside writable
  roots, the exact execution root is receipted, and network remains disabled;
  no model-fit, owner-acceptance, landing, commit, publication, or runtime
  activation claim is implied.

- A separate credential-bearing, content-addressed Wave 1 read-canary contour
  for KAG, stats, and decisions. It observes one exact loopback schema and
  owner-specific result-contract match, and preserves a successful structured
  response in a private content-addressed artifact for independent owner
  review, without inferring grounding, freshness, proof, acceptance,
  admission, or rollback. Canary receipts and result artifacts are now
  independently Ed25519-attested by a provisioned private stack signer so
  downstream owners can authenticate captures against a separately pinned
  public key instead of trusting caller-reproducible hashes and issuer fields.
  Every standalone stack-owned MCP package now reports
  its embedded application package version rather than the MCP SDK or stale
  ambient distribution metadata. A blocking source validator keeps each
  embedded version equal to its package manifest and requires the server
  constructor to invoke the version binding; decisions read annotations are
  explicit.
- `abyss-stack-mcp-observe` now atomically composes a five-minute production
  runtime observation from an immutable deployment receipt, the private
  deny-by-default organ registry, a committed fifteen-target owner-specific
  catalog, exact named user-systemd facts, and an optional owner-issued
  evidence overlay. It reads no credentials, performs no endpoint probes,
  excludes shared-bearer legacy contours, preserves every unsupported claim as
  unknown, and has a separately enabled two-minute user timer.
- Decision `ABYSS-STACK-D-0102` admits only exact read-only explicit-pull
  memory delivery in R1; shadow, canary, and agent-local seams remain disabled
  contracts without hidden persistence or effect authority.
- The memo federation seam now carries the C20
  `RuntimeDeliveryReceipt` source contract for content-minimized active-organ
  delivery evidence. Exact intent, plan, trigger, anchor, policy, admission,
  target, and evidence refs distinguish attempted, delivered, suppressed,
  expired, and failed states while forbidding persisted packet, prompt,
  memory, payload-digest, and error-detail content. Executable negative
  examples fail closed on stale authority, content retention, expiry, and
  consumer-binding drift; the contract grants no effect or memory authority
  and does not claim a live deployed service.
- Decision `ABYSS-STACK-D-0103` adds a neutral Codex hook-fragment compositor
  for independently usable owners. Explicit bindings, atomic private writes,
  composition receipts, backup, and exact rollback remain separate from
  owner semantics and Codex trust; no live hook activation is implied.
- A standalone `abyss-stack-mcp` source candidate now exposes a compact
  stack-owned runtime-evidence read plane and a credential-disjoint,
  non-executing plan-candidate plane. Typed contracts keep source, package,
  deploy, process, endpoint, registry, consumer-schema, canary, freshness, and
  rollback evidence separate; generated public examples are fictional, and
  source-owned user units remain unstarted until provenance, deployment
  parity, registry, consumer, canary, proof, and acceptance gates are met.
- The stack MCP candidate contour now avoids PostgreSQL on port `5432`, uses
  explicit port `5433`, provisions a source-and-lock-addressed Python runtime
  from exact artifact hashes before unit activation, coordinates each
  plane's lifetime shared lock against exclusive provisioning, rechecks unit
  state immediately before replacement, installs only from a private
  digest-matched package snapshot, rehashes installed runtime files and
  symlink targets before reuse, serializes MCP Configs sync and runtime
  publication with a separate source-projection lock, rejects a combined
  unit-link/provision transaction, and fails activation-plan preparation
  on unusable freshness, endpoint/process unreadiness, incompatible consumers,
  ungrounded canaries, or missing rollback proof. Concurrent first credential
  writes publish one atomically selected value without clobbering the winner.
- Published stack MCP schemas now encode conditional runtime invariants;
  freshness includes supporting-ref expiry, plan TTL cannot outlive any copied
  precondition, central proof binds the exact deployed-tree digest and running
  process identity as well as the source-tree digest and exact canary route,
  activation steps name the exact selected compatible consumer registration,
  and effect planes cannot be activated or restarted
  before their distinct contracts
  exist. Sync and deploy candidates now bind their distinct expected
  post-action tree digests, rollback denial binds the exact registry digest,
  and secret screening covers separator/camel credential names plus
  concatenated keys at recognized namespace or attribute boundaries without
  blocking ordinary word substrings, compact
  JWT values, and encoded URI path segments as well as
  userinfo/query/fragment surfaces. Rollback proof now binds every
  last-known-good restoration field including its distinct canary, and staged
  runtime entry-point shebangs are rebound before content-addressed
  publication. Provisioning and managed units clear ambient Python import roots
  and use isolated mode, while read catalog/inspection apply the earlier
  wall-clock/snapshot bound and downgrade a causally future observation
  envelope, link, freshness, or nested evidence timestamp to `blocked`;
  inspection also folds its selected effective link state into response
  freshness while preserving the raw owner claim. Existing equal
  read/candidate bearer values fail closed instead of collapsing the contours.
- Read payloads now propagate an expired observation envelope into their
  derived catalog/freshness/drift states, raw references reject the standard
  GitLab token-prefix families, and standalone runtime provisioning verifies
  that user systemd has loaded both expected fragments with the exact
  lock-aware `ExecStart` before it can replace the venv.
- Candidate result freshness now folds every copied plan link, and activation
  or rollback causality checks ignore unrelated consumers in favor of the
  exact proof-selected or last-known-good registration.
- Step-relevant deploy, consumer-registration, proof, acceptance, canary, and
  rollback targets now have to match evidence identities copied into and
  expiry-bounded by the candidate; proof and acceptance bind the named ref and
  declared owner in the same evidence item. Managed stack MCP launches also
  disable bytecode writes explicitly so isolated mode cannot mutate the
  measured runtime after provisioning.
- Secret screening now detects bounded provider-token patterns inside
  descriptive references and passphrase-bearing exact or namespaced keys;
  rollback restoration requires evidence bound to an absent consumer's exact
  registration target, and runtime reuse binds the bytes behind the fully
  resolved venv interpreter symlink chain.
- Rollback candidate preparation now relies on the usable, typed
  last-known-good rollback proof and no longer blocks on or copies canary
  evidence from the current deployment.
- Restart candidates now reject inactive processes instead of allowing the
  restart step to act as an ungated start path. They also carry and verify the
  central proof that binds their exact current source, package, deploy,
  process, schema, compatible consumer registration, canary route, and receipt.
- Managed stack MCP units now verify deployed source-and-lock identity and the
  complete measured runtime-content digest before every launch, while secret
  screening rejects unambiguous compound credential keys such as
  `aws_secret_access_key`, exact `credential`/`credentials` references, and
  AWS presigned credential/signature/session-token query keys. Final launch
  repeats verification while holding source-projection and runtime locks that
  remain live across `exec`, closing the sync-to-launch race.
- Rollback plans now admit fresh `rollback_required` failed-link evidence
  without weakening other blockers, while managed units execute only the
  digest-matched package installed in their provisioned venv.
- A local no-listener `aoa-agent-os-runtime` bridge now lets the `aoa-sdk`
  `AoARunner` drive three exact owner-pinned contours. `AOA-P-0011` retains
  two approvals, isolated preview, landing, rollback, and the existing
  governed runner; `AOA-P-0031` reviews a typed A2A return without executing a
  child; and `AOA-P-0032` proves partial degradation progress, durable pause,
  subprocess restore, and duplicate-safe resume. Original-owner input evidence
  remains owner-qualified, while eval verdicts, memory receipts, checkpoint
  acceptance, and final closeout remain with their stronger owners.
- The runtime descriptor, scenario-scoped `RuntimeProfile` approval
  projection, and compiled `RunPlan` must now agree exactly. All three golden
  success cycles enter the adapter from the installed public compiler v3
  chain without post-compilation plan mutation.
- A distinct, inert `aoa-routing-cutover` path now admits only a
  receipt-bound `aoa-sdk` canonical routing release with exact public-release
  runtime trust, verified subject-store bytes, explicit G5 authority, atomic
  verified predecessor rollback, a durable compatibility-rollback marker, and
  route-api closure proof with exact producer controls; failed rollback swaps
  remove their staged marker so the verified predecessor remains retryable,
  while process termination before, between, or after the swap steps is
  recovered from exact on-disk state. Live activation uses a durable prepared
  stage and recognizes every rename boundary, and file/directory `fsync`
  barriers make both activation and rollback recovery reboot-safe. Corrupt
  trust collections fail closed without crashing health. The path neither
  performs the owner switch when merged nor authorizes predecessor archival.
- A fail-closed `aoa-routing-canary` runtime adapter now verifies exact
  `aoa-sdk` subject-store bytes, latest `abyss-machine` `runtime_canary`
  admission, source/predecessor refs, and all-false G5 authority before
  reversible isolated or operator-authorized live-canary activation; route-api
  exposes `canary_ready` without turning the non-canonical mirror into ordinary
  runtime closure.
- The Tree of Sophia foundation laboratory now provides a loopback-only human
  review workbench for independent calibration, German source, and
  method-blind OCR candidate packets, with verified source-page routing,
  criteria-first review, candidate-prefilled correction, reviewer-declared
  language scope, atomic autosave and resume, human-readable edition/page
  routing, paste-ready private screenshot feedback, explicit human
  attestation, and a digest-bound frozen draft that cannot claim gold, source
  acceptance, or a general method ranking.
- Tiered KAG runtime materialization now admits exact-commit owner-family
  releases and 24-owner compositions through the `abyss-machine` trust gate,
  verifies direct or packed objects into a local content-addressed cache,
  preserves candidate/current/last-good state, advances exact rows, Qdrant
  owner collections, and Neo4j owner/owner-pair slices selectively, coordinates
  last-good rollback across all three projections, and exposes explicit
  delivery identity and degradation through the existing five-operation MCP
  ABI.
- `skills/abyss-self-diagnostic-spine` is now the admitted owner package for
  stack runtime diagnosis, with an explicit procedure contract and
  OS-user-profile exposure instead of a second repo-local copy.
- An explicit Gemma 4 E2B `llama-swap` tuning candidate now admits measured
  cold loads through the private `abyss-machine` owner socket, keeps proxy
  history bounded to zero, releases the model after idle, removes inherited
  static caps, and rolls back to the existing native-sleep overlay.
- Stack-owned MCP packages now retain portable stdio defaults while supporting
  explicit authenticated loopback shared Streamable HTTP owners on stable
  per-package ports, with source-owned systemd credential/template/bundle
  lifecycle and per-owner canary boundaries.
- New interactive Codex launches can use those shared owners through an
  idempotent, removable user-scoped Zsh integration that keeps the bearer out
  of shell configuration and leaves the managed binary and running sessions
  unchanged.
- Configs sync now supports non-mutating `--dry-run` previews and repeatable
  allowlisted `--item` selection while excluding source-control, bytecode, and
  test/tool cache residue from deployed runtime mirrors.
- A root `stats/` port now declares the live-capable, declaration-only selected
  service running-coverage question, while the service-selection readout keeps
  failed observation distinct from an observed zero and exposes the ratio over
  the full `selected_now` population.
- Repo-self KAG bundles can now be verified and materialized into atomic
  SQLite/FTS, versioned Qdrant, and versioned Neo4j runtime projections with a
  shared current receipt and source-return identities; owner-aware FTS and
  Qdrant filters are indexed, and new vector projections reuse unchanged
  embeddings before processing their document delta.
- `aoa-evals-mcp` now consumes the `aoa-evals` local-port inventory v2 read
  model, exposing source-contract-ready, stale, invalid, or absent local suite
  execution posture without running suite commands or widening the local-port
  write allowlist; v1 and unknown inputs fail closed to `absent`.
- `aoa-kag-mcp` now serves repo-self knowledge through five stable read-only
  operations over canonical, SQLite/FTS, Qdrant, and Neo4j adapters, with
  addressed resources, evidence traces, bounded context, and explicit
  canonical fallback during projection degradation.
- `aoa-stats-mcp` now provides a stack-owned read-only access plane for the
  central derived catalog, compact boundary refs, canonical owner inventory,
  owner-local measurement definitions, and transport-neutral packet
  compatibility without moving statistical meaning out of `aoa-stats` or its
  local owners.

### Changed

- The complete `tests` and `release` pytest selection now uses a four-process,
  file-aware work-stealing DAG with exact baseline, disjoint-union, observed
  selection, and final-verdict proofs. Duration hints affect order only; the
  explicit serial oracle remains available, and no xdist control thread enters
  fork-sensitive tests.
- External Codex runtime validation now memoizes only successful Draft 2020-12
  meta-validation keyed by exact bounded schema bytes. Files are still reread
  and freshly parsed, changed or invalid bytes fail closed, and every runtime
  value remains validated; repeated session and A2A transitions avoid the
  previous redundant meta-schema traversal.
- `Repo Validation` now runs branch candidates through the pull-request event
  only, retains the full postmerge `main` push proof, and cancels only an
  obsolete in-progress run for the same PR or ref when a newer head arrives.
- `abyss-machine-mcp` now requests the bounded owner-provided typing status
  projection instead of pulling the full detailed packet into every live/full
  machine brief. An exact missing-flag compatibility fallback keeps older host
  installs readable without masking any other owner-command failure.
- Routing federation health is now check-only over the admitted SDK-canonical
  materialization: ordinary sync cannot produce or repair routing bytes,
  governed execution no longer exposes a predecessor mutation target, and the
  active compatibility trial corpus routes current owner checks to `aoa-sdk`
  while retaining old case IDs only for log compatibility.
- Compact the diagnostic skill's global routing description while retaining
  capture, concrete target, evidence/freshness, bounded repair-handoff, and
  stored-packet review plus nearest-route distinctions in the host-visible
  prefix.
- Newly initialized Tree of Sophia OCR candidate reviews now use a
  backward-compatible v2 workbench protocol with a combined
  omission-plus-addition outcome and provenance-safe stand-off italic
  annotations; existing v1 sessions and frozen drafts stay byte-compatible.
- Thin-host service overlays now preserve service-native budgets and soft
  reclaim reservations while clearing hard cgroup CPU and memory ceilings from
  persistent owner services; explicit measured lab and disposable workloads
  remain the only routes for static ceilings.
- The Gemma 4 E2B `llama.cpp` lane now keeps its 4 GiB soft reclaim
  reservation but leaves residency release to native idle sleep instead of an
  8 GiB hard memory ceiling.
- The authenticated loopback MCP bundle now admits the source-owned
  `aoa-stats` wrapper, while Configs sync carries the stack-local `stats/` port
  and the service resolves that source route through the deployed stack root.
- The Intel worker overlay now protects the trusted OVMS embedding lane with a
  soft reclaim reservation and owner-native health/reload controls instead of a
  hard memory ceiling that can force private reclaim while host RAM is free;
  the resource-guard apply route also detects and recreates containers that
  retain a stale live ceiling after the rendered guard is removed.
- Validation and test commands now route through active `AGENTS.md` cards,
  command-owner docs, and the canonical lane manifest instead of being copied
  into decision records, landing logs, or the root audit contract; the dated
  service-optimization completion report and its systemd documentation link
  were removed after its durable routes had owners.

### Fixed

- The exact stack MCP restart-and-rollback pilot now accepts systemd's
  owner-only mode-`0400` `LoadCredential` projection of the canary Ed25519
  key, while the source key remains mode-`0600` and group/world-readable,
  foreign-owned, symlinked, or non-regular keys still fail closed. This lets
  both mandatory post-restart canaries use the isolated effect credential
  contour instead of rejecting systemd's read-only projection before probing.
- The configured session-memory HTTP smoke now keeps connect/write/pool and
  ordinary response reads plus the SSE handshake bounded, removes the read
  deadline only after its authenticated long-lived SSE GET is established,
  and preserves explicit 20-90 second per-tool MCP budgets, so valid calls no
  longer race httpx's five-second `ReadTimeout` without making handshakes or
  ordinary requests unbounded.
- Agent OS start/resume/recovery dispatch now compares its refreshed
  source/ABI observation with the immutable `RunPlan` before backend
  execution. Approval decisions must target the single current undecided
  request before any governed approval, event, status, or outcome mutation, so
  stale or second decisions cannot cancel an advanced or completed run.
- Federation routing health now accepts the stable current routing version
  fields, verifies exact mirror-manifest hashes, and reports source,
  artifact-identity, and subject-bound durable trust readiness instead of
  returning an unconditional green result for stale v1 bytes.
- `aoa-kag-mcp` canonical fallback now resolves portable-v3 family manifests
  when the logical v2 source-index path is intentionally absent, and service
  validation performs a real canonical portable read instead of checking only
  the static five-tool and nine-resource ABI.
- Session-memory MCP graph reads now keep neighborhood, timeline, and
  cooccurrence work on bounded indexed SQLite reads, while path, bridge,
  GraphRAG, explanation, evaluation, quality audit, and unresolved expansion
  return the exact owner command wrapped by canonical `abyss-machine resource
  launch` admission instead of starting hidden archive scans. Exact agent-event
  usage audits now use their existing indexed read model and defer broad
  consequence expansion through the same owner-admitted route.
- The diagnostic skill now resolves its exact `abyss-stack` owner package from
  the same-bundle OS source receipt, while the shared skill-projection
  validator no longer treats a repo-local diagnostic directory as canonical.
- `aoa-session-memory-mcp` now publishes and validates exact closed-world
  read-only annotations for every tool, allowing Codex approval policy to
  distinguish evidence reads from side-effecting MCP calls without a per-tool
  approval bypass.
- Shared MCP HTTP startup now fails closed without a valid host-local bearer;
  Codex receives only the named environment route, systemd loads the secret as
  a credential, and provisioning rejects symlinked secret paths without
  changing permissions on an existing shared secret root.
- `aoa-session-memory-mcp` transport preflight now recognizes fresh or stale
  loopback shared owners, rejects remote, credential-bearing, and malformed
  HTTP endpoints without crashing, and does not require a per-Codex child for
  a configured shared owner.
- User-unit installation preserves existing `/dev/null` masks instead of
  replacing an operator-disabled unit while linking the managed allowlist.
- Decision graph freshness now distinguishes local cache parity from checkout
  source posture, preserves lag/dirty warnings, and no longer treats arbitrary
  worktree directory names as separate repositories.
- Source-to-Configs sync and parity now include stack-owned `mcp/` packages and
  root `schemas/`, so deployed MCP services cannot silently remain older than
  their merged source packages.
- The `aoa-stats` live-refresh user-unit adapter now watches only the six
  currently admitted owner-local receipt surfaces and delegates registry
  selection to the deployed `aoa-stats` refresh command instead of pinning the
  retired runtime-wave receipt and a sibling-internal registry path.
- `aoa-session-memory-mcp` now preserves producer-classified structured skill
  selection/load candidates and session-qualified task-episode refs across
  compact audit, usage-chain, and dossier packets, while keeping `loaded`
  distinct from skill reads, procedure execution, completion, and
  effectiveness; bounded action summaries retain stronger semantic buckets
  before weak mention, cooccurrence, or context buckets.
- `aoa-session-memory-mcp` compact skill audit, usage-chain, neighborhood, and
  dossier packets now preserve producer-owned candidate states, action
  semantics, evidence refs, and separately bounded rejected foreign
  correlations without exposing raw transcript bodies or claiming a skill
  invocation/effectiveness verdict.
- `aoa-session-memory-mcp` now exposes a read-only transport preflight route
  and CLI command, so agents can distinguish stale/missing Codex MCP transport
  from broken `.aoa` indexes when direct tool calls return `Transport closed`.
- `aoa-session-memory-mcp` now auto-reloads its `core.py` implementation for
  existing tools and reports already-running stale Codex MCP transports in the
  service validator, so freshness/provider packet fixes do not silently depend
  on manual process restarts.
- `aoa-session-memory-mcp` entity usage audit and neighborhood routes now
  return bounded MCP payloads by default, with compact samples, omitted counts,
  freshness summaries, and a full-evidence expansion command instead of dumping
  bulk archive events into agent context.
- `aoa-session-memory-mcp` now exposes a read-only projection-status route over
  the latest `.aoa projection-catchup` completeness diagnostic, so agents can
  see post-classifier/schema projection coverage without running maintenance
  through MCP.
- `aoa-session-memory-mcp` compact status now preserves the latest
  search-shard materialization timings and bounded slow-session samples, so
  agents can see which real session made maintenance slow without opening the
  full `.aoa` report.
- `aoa-session-memory-mcp` compact status now preserves `.aoa` search-shard
  raw-text fallback dependency signals, including blocked shard counts and
  scoped full-text expansion commands, so agents can choose the right bounded
  search route without loading the full maintenance packet.
- `aoa-session-memory-mcp` entity inventory responses now stay bounded for
  wide skill/MCP/hook/tool/API route probes by returning compact sample refs,
  a route packet, sample budget/omitted counts, and an explicit expansion
  command instead of heavy atlas entry paths in every sample.
- Runtime config artifact validation now promotes release-ready evidence through
  the OS Abyss registry, materializes subject-store evidence under ignored
  `dist/`, requires source/trust-root matching and a fail-closed runtime
  trust-gate allow verdict before exposing a latest bundle read-model, and
  makes the manifest declare subject-store admission before runtime consumers
  can use the bundle.
- Release validation now renders the public-safe `substrate` config as an OS
  Abyss artifact bundle and verifies ABI, SBOM, SLSA/in-toto, and
  signature-decision sidecars through `abyss-machine`.
- `aoa-session-memory-mcp` now rejects unsupported retrieval recipes before
  dispatching to the archive, keeping the MCP retrieval allowlist as the local
  gate instead of relying on downstream archive errors.
- `aoa-memo-mcp` now checks colon-suffixed local payload refs like
  `README.md:12` as local paths instead of letting `urlparse` classify them as
  symbolic URI schemes.
- Decision graph builder and `aoa-decisions-mcp` now derive the default
  `abyss-stack` checkout from the running source tree instead of a private
  `/home/dionysus/src/abyss-stack` path.
- `aoa-memo-mcp` now rebuilds the containing local memo port index after
  rejected reviewed-intake receipts, keeping receipt indexes fresh for invalid
  or mismatched export repos.
- `aoa-memo-mcp` briefs now honor read-only workspace memory routes even when a
  physical memo port exists, avoiding candidate-write guidance that the tool
  will reject.

## [0.4.0] - 2026-06-07

### Summary

- root direction, release history, and decision rationale now follow an
  explicit AoA-style role split adapted to the `abyss-stack` runtime substrate
- root `README.md` is now a compact source-checkout front door instead of a
  current-state inventory or package-local surface ledger
- decision records are now validator-backed and indexed as durable rationale,
  not remembered as a loose convention from previous refactor passes
- validation, script, and test topology now have explicit command authority,
  inventories, and lane guards before the large stack validator is split
- root `ROADMAP.md` is now a runtime-wide horizon surface instead of a mixed
  landing history, backlog, and release-contour document
- root `docs/` now uses role-named districts instead of a flat surface list,
  preserving the AbyssOS source/runtime split in the folder topology itself
- the Intel workstation route now has explicit service-selection docs, a Gemma
  4 E2B `llama.cpp` Vulkan lane, an opt-in Qwen3 rerank API profile, thin-host
  guard overlays, a protected TTS keep-warm timer, and the first source-linked
  RAG orchestration profile
- the observability route now adds internal-only Loki and Grafana Alloy so
  PromQL, LogQL, dashboards, and alerting live in the same explicit profile
- MCP access-plane and agent-skill projection surfaces now include the current
  decision-lane and session-memory operator routes needed by this release line

### Added

- `docs/decisions/AGENTS.md`, `docs/decisions/TEMPLATE.md`,
  `scripts/decision_indexes.py`, `scripts/generate_decision_indexes.py`,
  `scripts/validate_decision_records.py`, and `tests/test_decision_records.py`
  as the local canonical decision-record contract and validation lane
- `docs/decisions/ABYSS-STACK-D-0017-direction-history-decision-surface-roles.md` as
  the rationale for the `ROADMAP.md`, `CHANGELOG.md`, and `docs/decisions/`
  role split
- `docs/routes/START_HERE_ROUTE_CONTRACT.md` as the source-checkout route-mode
  contract for root entry surfaces
- `docs/{routes,runtime,install,operations,profiles,governance,legacy}/README.md`
  as short district maps for repo-wide documentation
- `docs/RELEASING.md` as a compatibility route for release tooling and older
  links, pointing to the authoritative `docs/governance/RELEASING.md` flow
- `docs/decisions/ABYSS-STACK-D-0020-docs-district-topology.md` as the rationale for
  the docs district split
- initial `mechanics/` topology with runtime lifecycle, config projection,
  machine fit, inference pilots, federation seams, governed execution,
  diagnostic spine, and runtime repair package cards
- follow-up `mechanics/agon-runtime` and `mechanics/experience-runtime`
  archive-containment packages with provenance and `legacy/` indexes
- archive-containment bridges for `mechanics/runtime-repair` and
  `mechanics/inference-pilots`, including quiet pilot bridge commands
- stack-side `abyss-machine` bridge capture via `scripts/aoa-machine-bridge`,
  with `Logs/machine-bridge/` latest/history/index routes and package-local
  contract docs
- root `systemd/` route card and README so user-unit skeletons no longer sit
  behind an unowned top-level folder
- `.agents/spark/README.md` as the repo-local route surface for the fast-loop
  lane
- `scripts/README.md` as the stable command map for root wrappers, validators,
  and their mechanic ownership routes
- `docs/README.md` and `tests/README.md` as root district indexes for
  repository docs and repo-level validation
- `.agents/` route README and `.github/GITHUB_SURFACE.md`, plus
  `.agents/AGENTS.md` for repo-local agent overlays and GitHub-native route
  mapping that does not compete with the homepage README
- root `DESIGN.md` and `DESIGN.AGENTS.md` surfaces, adapting the AoA route-card
  pattern to the `abyss-stack` runtime substrate
- `mcp/services/AGENTS.md`, `mcp/services/README.md`, and
  `docs/decisions/ABYSS-STACK-D-0032-mcp-services-topology.md` as the canonical MCP
  service-package topology for `aoa-memo-mcp`
- `mcp/services/abyss-machine-mcp/` and
  `docs/decisions/ABYSS-STACK-D-0036-abyss-machine-mcp-access-plane.md` as the
  stack-owned, read-only MCP access plane over `abyss-machine` host read models
- `memo/` reviewed-intake packet for the post-2026-05-22 MCP access-plane
  expansion, preserving that `abyss-stack` owns service packaging while
  `aoa-evals`, `abyss-machine`, and `aoa-memo` keep their respective authority
- `docs/runtime/SERVICE_SELECTION.md` as the source-level service-selection
  guide for lean Intel, full Intel, optional workflows, tools, observability,
  reranking, and protected speech routes
- `loki` and `alloy` in `compose/modules/60-monitoring.yml`, with public-safe
  Loki, Alloy, Grafana datasource, Prometheus scrape, alert, layout, probe,
  service-selection, and decision-record coverage for LogQL observability
- `.agents/skills/aoa-decision*` and `.agents/skills/aoa-memo-writeback` as
  repo-local projection routes into the sibling `aoa-skills` canon for
  decision lookup, decision correction/creation, and memory writeback work
- `compose/modules/45-rerank-api.yml`, `compose/profiles/reranking.txt`, and
  `config-templates/Services/rerank-api/` for the explicit localhost-only
  OpenVINO Qwen3 reranker wrapper
- `compose/modules/46-rag-api.yml`, `compose/profiles/rag.txt`,
  `compose/tuning/rag.thin-host.yml`,
  `config-templates/Configs/rag/`, and
  `config-templates/Services/rag-api/` for the first lightweight RAG,
  Agentic-RAG trace, and DAG manifest orchestration layer over existing stack
  services
- `compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml` for the candidate
  Gemma 4 E2B text lane on the Intel 285H class through `llama.cpp` Vulkan
- `compose/tuning/storage.intel-285h.resource-guard.yml`,
  `compose/tuning/observability.thin-host.yml`,
  `compose/tuning/tools.thin-host.yml`, and
  `compose/tuning/workflows.thin-host.yml` as explicit resource guard overlays
  for selected services
- `systemd/user/abyss-tts-keepwarm.service` and
  `systemd/user/abyss-tts-keepwarm.timer` for bounded TTS warmth through the
  existing protected host TTS server
- `docs/decisions/ABYSS-STACK-D-0028-intel-inference-and-rerank-service-selection.md`
  as the rationale for the current Gemma, OVMS embeddings, Qwen3 reranking,
  protected TTS, and optional-service split
- `docs/decisions/ABYSS-STACK-D-0038-canonical-decision-ids-and-indexes.md`
  and generated `docs/decisions/indexes/` read models for stable
  `ABYSS-STACK-D-####` decision lookup
- `docs/validation/` and `docs/testing/` as the source-owned districts for
  validation command authority, validator topology, script topology, test
  topology, lane manifests, and machine-readable inventories
- `scripts/validation_lanes.py`, `scripts/ci_gate.py`, and topology tests for
  manifest-backed validation lanes, script surfaces, validator surfaces, and
  test inventory coverage
- `scripts/validators/script_surface.py` as the first focused owner module
  extracted from `scripts/validate_stack.py`
- `scripts/validators/source_hygiene.py` as the focused source/runtime hygiene
  module extracted from `scripts/validate_stack.py`
- `scripts/validators/source_structure.py` as the focused required-file and
  root residual topology module extracted from `scripts/validate_stack.py`
- `scripts/validators/service_selection.py` and focused tests for the runtime
  service-selection policy and screenshot inventory validator split
- `scripts/validators/sync_parity.py` and focused tests for sync-managed
  source enumeration and source/deployed Configs parity
- `scripts/validators/questbook_surface.py` and focused tests for quest schema
  envelopes, quest source topology, generated quest examples, and RPG runtime
  read-model guards
- `scripts/validators/federation_surface.py` and focused tests for federation
  runtime-loaded config input coverage, upstream bridge template posture, and
  active-vs-legacy bridge language, and federation landing docs
- `scripts/validators/federation_runtime_seams.py` and focused tests for
  memo/eval/playbook/KAG runtime seam docs, bounded export examples, and A2A
  handoff posture
- `scripts/validators/diagnostic_spine.py` and focused tests for diagnostic
  surface docs, schemas, examples, generated catalog refs, overlay skill
  posture, and repair handoff readiness
- `scripts/validators/runtime_hygiene.py` and focused tests for runtime
  gateway cache/usage status-readout docs, schemas, examples, and
  readiness-only doctor split posture
- `scripts/validators/machine_fit.py` and focused tests for reference-platform,
  host-facts, machine bridge, machine-fit record, freshness gate, and
  platform-adaptation posture
- `scripts/validators/return_policy.py` and focused tests for return-policy
  config routes, render-truth autonomy route refs, and runtime return schema
  identity
- `scripts/validators/branch_policy.py` and focused tests for CONTRIBUTING
  branch-policy routing, canonical `main` posture, branch retirement language,
  and source/runtime checkout distinction
- `scripts/validators/root_routes.py` and focused tests for root design cards,
  start-here route exposure, front-door route modes, and command-authority
  handoff language
- `scripts/validators/decision_surface.py` and focused tests for decision
  route cards, template shape, validator/generator handoffs, and
  `test_decision_records.py` route exposure
- `scripts/validators/mechanics_topology.py` and focused tests for mechanics
  atlas routes, package card headings, part required files, active part names,
  archive routes, and marker-only artifact posture
- `scripts/validators/profile_topology.py` and focused tests for
  composition-first profiles and presets, compose module dependency guards,
  profile workflow rehearsal, sidecar/n8n/warmup posture, and active profile
  route language
- `scripts/validators/runtime_route_contracts.py` and focused tests for stale
  deployed-root bans, root README route focus, runtime/federation route docs,
  and governed policy/catalog envelope checks
- `scripts/validators/inference_pilot_compatibility.py` and focused tests for
  active local-trials bridge posture, preserved gate IDs, legacy W0-W4 metadata
  containment, and active LangGraph/llama.cpp compatibility language
- `scripts/validators/active_topology_language.py` and focused tests for
  retired phase/wave/seed wording, RPG runtime projection language, playbook
  activation allowlist drift, and route-api bridge language
- `scripts/validators/agent_skill_projection.py` and focused tests for
  repo-local `.agents/skills` projection, sibling `aoa-skills` targets,
  checkout-safe target files, local overlays, and diagnostic overlay installs

### Changed

- `scripts/validate_stack.py` is now a root validation orchestrator instead of
  a public compatibility-wrapper API; focused tests call validator modules
  directly and legacy root-named test routes were replaced with
  owner-shaped test names.
- `aoa-evals-mcp` now treats explicit `runtime-candidate-export:<id>` refs as
  strict runtime export selectors and filters weak route tokens, preventing
  unrelated runtime candidate exports from being attached to eval-need
  proposals.
- root `AGENTS.md` now follows the canonical route-card shape and routes future
  passes through runtime design and agent-surface design before local work
- top-level route docs now point runtime-move work through the mechanics atlas
  before entering package-specific docs, scripts, schemas, or config surfaces
- flat root docs moved into role-named districts: route contracts under
  `docs/routes/`, runtime topology under `docs/runtime/`, source install under
  `docs/install/`, operations under `docs/operations/`, profile selection under
  `docs/profiles/`, governance under `docs/governance/`, and preserved old
  references under `docs/legacy/`
- source-managed runtime component references now use current inspected
  `version-tag@sha256` pins across storage, orchestration, inference,
  monitoring, and helper service bases, while stateful datastores stay on their
  current compatible lines unless a separate migration packet promotes a major
  jump
- noisy Agon and experience archival artifacts, including late-found experience
  job/worker/storage-plan docs, moved out of flat root districts into
  package-local `legacy/` homes with validators and tests following the move
- runtime repair chaos receipts and preserved pilot files moved out of flat
  root districts into package-local `legacy/` homes with route bridges
- GitHub mirror hygiene now keeps the repository source/install-only by
  ignoring obvious local runtime artifacts and failing validation on tracked
  live/private/heavy files while preserving public examples and fixtures
- part-owned mechanic docs now live under their owning `parts/<part>/docs/`
  homes for config projection, diagnostic spine, governed execution, inference
  pilots, and runtime lifecycle, with validators, tests, quest anchors, and
  generated diagnostic refs following the move
- config-projection and runtime-lifecycle operator commands now keep stable
  root `scripts/` wrappers while their implementation bodies live under the
  owning mechanic parts, with validator and CI shellcheck coverage for the
  wrapper/backend bridge
- remaining root operator commands now follow the same wrapper/backend pattern
  across diagnostic spine, machine fit, inference pilots, federation seams,
  governed execution, runtime lifecycle, runtime repair, and Windows bridge
  surfaces
- `release_check.py` now uses synthetic Configs parity by default, keeping
  source release audits independent from stale live runtime mirrors unless
  `--parity-mode live` is requested
- `release_check.py` now reads the release command sequence from
  `docs/validation/validation_lanes.json`, and GitHub `Repo Validation` routes
  reusable release and shellcheck commands through `scripts/ci_gate.py`
- `aoa-session-memory-mcp` now reports a live SQLite graph store separately
  from a missing exported sidecar, keeps bounded graph maintenance in the MCP
  plan, and leaves full sidecar export under explicit offline operator commands
- `validate_stack.py` now delegates script/operator-wrapper validation to the
  focused `scripts/validators/script_surface.py` module while keeping root API
  compatibility for existing tests and callers
- `validate_stack.py` now delegates public mirror hygiene, host-local checkout
  path bans, moved mechanic doc refs, and stale active sibling root checks to
  `scripts/validators/source_hygiene.py`
- `validate_stack.py` now delegates required source-file checks, managed unit
  skeleton checks, and residual root/doc district topology guards to
  `scripts/validators/source_structure.py`
- `validate_stack.py` now delegates service-selection policy and screenshot
  inventory checks to `scripts/validators/service_selection.py`
- `validate_stack.py` now delegates sync-managed item coverage, runtime
  Configs mirror checks, and source/deployed parity to
  `scripts/validators/sync_parity.py`
- `validate_stack.py` now delegates questbook, quest source, generated quest
  example, and RPG runtime read-model checks to
  `scripts/validators/questbook_surface.py`
- `validate_stack.py` now delegates federation required runtime input coverage
  upstream compatibility bridge template/language checks, and federation
  landing-doc guards to
  `scripts/validators/federation_surface.py`
- `validate_stack.py` now delegates memo/eval/playbook/KAG runtime seam export
  and advisory-route guards to `scripts/validators/federation_runtime_seams.py`
- `validate_stack.py` now delegates diagnostic-spine surface contracts to
  `scripts/validators/diagnostic_spine.py`, while the generated diagnostic
  catalog lists the focused module and test in its validation refs
- `validate_stack.py` now delegates runtime gateway cache and usage
  status-readout contracts to `scripts/validators/runtime_hygiene.py`
- `validate_stack.py` now delegates machine-fit evidence posture checks to
  `scripts/validators/machine_fit.py`
- `validate_stack.py` now delegates return-policy runtime contract checks to
  `scripts/validators/return_policy.py`
- `validate_stack.py` now delegates branch-governance policy checks to
  `scripts/validators/branch_policy.py`
- `validate_stack.py` now delegates root design and entry-route checks to
  `scripts/validators/root_routes.py`
- `validate_stack.py` now delegates decision-surface route checks to
  `scripts/validators/decision_surface.py`
- `validate_stack.py` now delegates mechanics topology checks to
  `scripts/validators/mechanics_topology.py`
- `validate_stack.py` now delegates runtime profile topology checks to
  `scripts/validators/profile_topology.py`
- `validate_stack.py` now delegates runtime route contract checks to
  `scripts/validators/runtime_route_contracts.py`
- `validate_stack.py` now delegates inference-pilot compatibility checks to
  `scripts/validators/inference_pilot_compatibility.py`
- `validate_stack.py` now delegates active-topology language checks to
  `scripts/validators/active_topology_language.py`
- `validate_stack.py` now delegates agent skill projection checks to
  `scripts/validators/agent_skill_projection.py`
- `compose/AGENTS.md` now routes module dependency contract changes to
  `scripts/validators/profile_topology.py`
- model-card docs no longer carry host-local source checkout links, and
  `validate_stack.py` now blocks that portability drift while still allowing
  the canonical deployed runtime root references
- the local diagnostic-spine skill overlay now points at current part-local
  diagnostic surfaces, and `validate_stack.py` blocks stale moved mechanic doc
  references
- active mechanics route docs now keep old family labels in provenance,
  contract paths, and bridges instead of package-active prose
- quests now use lane/state source topology under `quests/<lane>/<state>/`,
  with public-safe catalog and dispatch examples generated from owner-local
  quest helpers instead of flat root quest files
- `FIRST_RUN` now routes optional local model trials to inference-pilot and
  machine-fit surfaces instead of spelling the old qualification runner
  as part of normal bootstrap
- `aoa-local-ai-trials` now keeps its preserved local-trials runner under
  `mechanics/inference-pilots/legacy/trials/artifacts/scripts/` with active
  compatibility bridge and role-level adapter surfaces in `parts/local-trials/`
- root residual route surfaces were tightened: the audit contract now lives at
  `docs/routes/AUDIT.md`, the Spark fast-loop lane lives under `.agents/spark/`, and
  validators block those root-level residual paths from returning
- LangGraph and llama.cpp promotion surfaces now treat preserved runtime/edit
  gate IDs as compatibility wire IDs behind role-level adapter names, with a
  validator guard against archived stage prose returning
- federation seams now keep upstream eval and playbook compatibility names in
  `parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md` while active route
  docs use clean local route names
- autonomy status now routes preserved long-horizon and bounded-autonomy
  artifact names through explicit index constants
- active workspace sibling defaults and repo-local skill symlinks now route
  through `/srv/AbyssOS/<repo>`, with validation blocking stale active
  `/srv/<repo>` sibling roots outside legacy archives
- Agon dry-run runtime kernels now live as an active
  `mechanics/agon-runtime/parts/runtime-kernels/` substrate with quiet
  definitions, validators, tests, examples, schemas, generated registries, and
  recurrence observation manifests; experience-runtime records remain
  archive-only with an explicit distillation stop-line
- runtime compatibility names are now isolated behind explicit upstream
  contract fields and compatibility maps for eval templates, memo contradiction
  sidecar inputs, A2A return dry-runs, playbook automation plans, and Dionysus
  RPG prep-pack handoffs
- upstream compatibility IDs now flow through
  `Configs/federation/upstream-compatibility-bridge.json` instead of being
  repeated in route-api, exporter, repair, layout, and federation config
  surfaces
- inference-pilot trial compatibility now uses the quiet active bridge
  `parts/local-trials/trial_compatibility_bridge.py`, and the LangGraph
  dependency manifest lives in `parts/langgraph-pilot/requirements.txt`
  instead of the root command-wrapper directory
- all mechanics packages now carry the full package-card layer
  `DIRECTION.md`, `PROVENANCE.md`, `ROADMAP.md`, and `LANDING_LOG.md`, with
  `validate_stack.py` enforcing the shared card spine
- residual quest frontier state now closes the profile machine-fit packet,
  machine-fit follow-through packet, RPG runtime materialization packet, and
  diagnostic runtime packet while preserving lane-local `done/` records; the
  route-api health and closure stop-line is now also recorded as a closed
  operator-gated live runtime cutover repair
- `aoa-install-systemd` now supports durable host-local runtime selection
  drop-ins with `--preset`, `--profile`, and `--restart-now`; the live
  federation repair preserves `intel-full` and layers `federation` instead of
  narrowing the machine to a federation-only preset
- root `ROADMAP.md` now has explicit authority, update rules, runtime horizons,
  stronger-surface routing, and future triggers so it no longer carries
  mechanic-local landing history or release history as roadmap law
- root `README.md` now routes by entry need, claim type, mechanics package, and
  technical district while sending detailed current state to `ROADMAP.md`,
  `CHANGELOG.md`, `docs/decisions/`, mechanic packages, and `docs/operations/RUNBOOK.md`
- root `README.md` now points validation readers to the broad release gate and
  local command authority surfaces instead of carrying package-specific command
  blocks
- `CHANGELOG.md` now records this role split as release-visible history instead
  of carrying the rationale itself
- all existing decision records now use full canonical `ABYSS-STACK-D-####`
  filenames, in-file decision IDs, `Index Metadata`, and generated lookup
  indexes, with `scripts/release_check.py` running the decision validator before
  the wider release audit
- `aoa-doctor`, `aoa-status --autonomy`, and `aoa-diagnose` now keep the
  machine bridge honest after the docs refactor: source-root detection uses
  `docs/install/DEPLOYMENT.md`, and doctor warns on stale or host-mismatched
  machine-fit and machine-bridge records
- n8n workflow automation now lives behind an explicit `workflows` profile;
  `substrate` and current presets stay workflows-free until a later operator
  decision promotes or retires that layer
- the source-owned default runtime profile is now `substrate`, containing
  storage only, while `local-worker` carries the canonical
  `llama.cpp` plus `langchain-api` worker layer and `core` remains a
  compatibility bundle
- root docs, profile docs, CI rehearsal, the checked-in user-unit skeleton, and
  validation now preserve the split between working substrate, local-worker,
  and richer live runtime selections
- retained Ollama and LiteLLM modules now route through an explicit
  `fallback-gateway` profile, while module/profile README surfaces classify
  substrate, workflow, worker, fallback, projection, helper, visibility, and
  pilot rings
- active render, diagnostic, curation, and machine-fit packet examples now use
  `substrate`, `local-worker`, `fallback-gateway`, or explicit presets instead
  of teaching `core` as the default runtime base
- `aoa-warmup` is now profile-aware across local-worker and fallback modules:
  `llama.cpp` can warm by default, while retained Ollama warmup requires
  explicit `AOA_OLLAMA_WARMUP_ENABLED=true`
- named presets now expand through explicit `substrate + local-worker` or
  `substrate + intel-worker` layers, while broad `agentic` and `intel` profiles
  remain compatibility routes instead of hidden preset bases
- `aoa-machine-fit` now resolves preset membership from the source checkout
  before falling back to deployed `Configs`, so stale live mirrors remain parity
  drift instead of changing the source-owned runtime recommendation
- source-managed systemd unit skeletons now have explicit user and privileged
  support allowlists, with install routes that link or copy units without
  starting, stopping, enabling, disabling, masking, or restarting services
- profile endpoint rendering, smoke probes, validation, profile docs, runtime
  storage docs, and model cards now know about the `reranking` add-on and the
  dedicated `rerank-api` service
- `rerank-api` now has configurable idle unload
  (`AOA_RERANK_IDLE_UNLOAD_SEC`, default `900`) plus a localhost
  `POST /admin/unload` route so occasional reranking does not keep the
  OpenVINO reranker resident forever
- `rerank-api` can exit after idle unload
  (`AOA_RERANK_EXIT_AFTER_IDLE_UNLOAD=true`) so container restart returns
  allocator-held OpenVINO memory to the host instead of relying only on
  in-process object deletion
- `aoa-llamacpp-pilot` can capture a lightweight live tuning snapshot packet
  from an existing `llama.cpp` service without starting or stopping services
- source-managed systemd unit skeletons now use normalized `file:///`
  documentation links, and the automatic power-profile support unit routes
  through the bounded `abyss-machine mode reconcile --light` command
- `abyss-nervous-semantic-maintain.timer` no longer uses `OnActiveSec=10min`,
  so user systemd reloads do not create an extra near-term semantic rebuild
  trigger outside the intended boot and 90-minute cadence
- host-local source-checkout validation now matches only the exact
  `/home/<user>/src/abyss-stack` path segment, avoiding false positives for
  sibling paths such as `abyss-stack-docs`
- the memory MCP access plane now lives under
  `mcp/services/aoa-memo-mcp/`, with route cards, validators, local memo
  receipts, and sibling memory-port references following the canonical service
  path

### Included in this release

Cross-check source: first-parent history, merged PRs, release-note follow-ups,
and the repository diff from `v0.2.2` through the published `v0.4.0` tag.

- root and route surfaces: nested `AGENTS.md` guardrails, slim root `AGENTS`,
  source-only mirror posture, GitHub surface separation, branch policy,
  release/governance docs, route-mode README, design surfaces, roadmap routing,
  docs district topology, and source/runtime path boundaries
- mechanics topology: package-card spines, part-local operator backends,
  package-local legacy containment, active-vs-archive language, quiet bridge
  routes, and package docs for config projection, runtime lifecycle, machine
  fit, inference pilots, federation seams, governed execution, diagnostic
  spine, runtime repair, Agon runtime, and experience runtime
- runtime profiles and services: `substrate`, `local-worker`, `intel-worker`,
  `fallback-gateway`, `workflows`, `tools`, `reranking`, `rag`,
  `speech-fast-experimental`, Gemma 4 E2B `llama.cpp` tuning, Qwen3 reranking,
  RAG orchestration, BabelVox/OpenVINO TTS, resource-guard overlays, and
  internal-only Loki/Alloy observability
- systemd and host-operation surfaces: source-managed user and system unit
  skeletons, service install routes, smoke/internal probes, warmup/status/log
  wrappers, resource-guard application, host-facts, machine-fit, platform
  adaptation, Windows/WSL bridge scripts, protected TTS warmth, and
  `abyss-machine` read-only bridge integration
- MCP access planes: `aoa-memo-mcp`, `aoa-evals-mcp`, `abyss-machine-mcp`,
  `aoa-session-memory-mcp`, and `aoa-decisions-mcp`, including memo port
  intake, corpus-backed memo search, memory writeback packet routing,
  workspace-map port discovery, runtime export filtering, SQLite graph-store
  sidecar posture, and read-only decision graph impact packets
- decision and graph surfaces: canonical `ABYSS-STACK-D-####` records, generated
  decision indexes, generated decision graph, workspace decision graph schemas,
  graph builder/validator scripts, modeled decision-surface list contracts,
  route-anchor impact packets, and decision-surface coverage guards
- federation and runtime seams: effective runtime input alignment,
  route-api/federation bridge compatibility IDs, eval/playbook/memo/KAG seam
  contracts, synchronized bridge eval templates, sibling mirror topology for
  aoa-agents, aoa-memo, and aoa-playbooks, and active legacy-archive
  dependency removal
- quests, memo, and recurrence read models: quest lane/state topology, quest
  examples and schemas, memo intake/receipts/candidates, reviewed forwarding
  receipts, recurrence manifests, diagnostic catalogs, degradation receipts,
  repair-safe closeout, A2A return dry-run, and memo contradiction sidecar
  validation
- validation and CI: `ci_gate.py`, release-check synthetic Configs parity,
  command-authority manifests, script/test/validator inventories, focused
  validator modules, nested AGENTS validation, schema contracts, compose/RAG
  contract tests, service-selection tests, decision-record tests, workspace
  decision-graph tests, Windows host bridge CI, and GitHub Repo Validation

### Validation

The release was verified through the then-current source, topology, generated,
test, and release lanes. Exact commands remain in the active validation owner
surfaces rather than this historical log.
- GitHub `Repo Validation` and `validate-windows-host-bridge` on the release
  landing PRs

### Notes

- this pass changes source-owned docs, validators, and tests only; it does not
  mutate live `/srv/AbyssOS/abyss-stack` runtime state or private machine state

## [0.2.2] - 2026-04-23

### Summary

- this patch lands Agon duel-kernel runtime records, event-log models,
  mechanical-trial run registries, and hash-chain quest surfaces while keeping
  those records bounded to runtime-owned infrastructure truth
- Experience watchtower, certification/deployment storage, federation harvest,
  adoption worker, retention, rollback, KAG promotion, pattern registry, and
  assistant release-lifecycle stack contracts are added for the current release
  line
- `abyss-stack` remains the source-authored runtime layer; deployed state
  still becomes live only through the configured runtime mirror and operator
  process

### Added

- Agon Wave XII duel runtime kernel surfaces, duel event logs, stop-lines,
  registry generation, and source/deployed recurrence manifests
- Agon Wave XIII mechanical-trial runtime records, event-log examples,
  trial-run registries, and runtime stop-lines
- Experience watchtower runtime records plus archived federation/adoption worker
  plans, runtime storage plans, canary probes, rollback jobs, KAG promotion
  jobs, and pattern-registry service records

### Changed

- runtime review follow-up drift, event-log schema checks, mechanical-trial
  contract checks, long-horizon pilot record posture, federation runtime review
  contracts, and source/deployed parity expectations were tightened

### Validation

The release was verified through the then-current release route.

### Notes

- this patch updates source-owned runtime contracts and public-safe docs only;
  it does not claim live deployment mutation from the source checkout

## [0.2.1] - 2026-04-19

### Summary

- this patch adds archived chaos runtime recovery, memo contradiction sidecars,
  and A2A return dry-run adapters across the runtime layer
- federated-consumer warnings, release parity CI, and roadmap/current-direction
  docs are tightened around the current runtime contour
- `abyss-stack` remains the source-owned runtime layer, with deployed truth
  still landing through the `Configs` mirror

### Added

- runtime chaos recovery surfaces, an A2A return closeout dry-run
  adapter, and memo contradiction runtime-sidecar coverage

### Changed

- federated-consumer warning posture, recall/contradiction bridge wiring,
  release parity CI safety, and CI/protection surfaces are aligned with the
  current runtime release line

### Validation

The release was verified through the then-current release route.

### Notes

- this patch extends bounded runtime recovery and advisory posture without
  claiming live deployment mutation from the source repository alone

## [0.2.0] - 2026-04-10

### Summary

- this release adds diagnostic-spine contracts, source-rooted mirror canaries, federated advisory seams, winner-promotion loops, and new OVMS/chat/ToS-graph runtime lanes
- llama.cpp fallback and tuning posture are hardened while runtime docs and AGENTS guidance are aligned around parity, support boundaries, and bounded advisory ownership
- `abyss-stack` remains source-authored on the runtime layer, with deployed state becoming live only after sync into the `Configs` mirror

### Validation

The release was verified through the then-current release route.

### Notes

- detailed runtime substrate, generated-surface, operator-surface, and parity-check coverage for this release remains enumerated below under `Added`, `Changed`, and `Included in this release`

### Added

- diagnostic-spine runtime seam, diagnostic surface-catalog capsule,
  reviewed-diagnosis bridge refs, and repair-handoff companion alignment
- source-rooted mirror canary plus parity-aware deployment verification for
  the deployed `Configs` mirror
- federated advisory seam presets and live checks, overlay skill installs,
  runtime winner-promotion loop, and checkpoint closeout bridge install in the
  repo skill surface
- Intel OVMS text-lab lane, Qwen3/OVMS model cards, route-first ToS-graph UI,
  preview-only curation slice, and a generic runtime chat seam

### Changed

- added llama.cpp runtime fallback for AVX512-less hosts and hardened
  llama.cpp env compatibility and tuning seams
- aligned runtime docs and AGENTS guidance with current support posture, via
  negativa runtime checks, and bounded advisory/runtime ownership

### Included in this release

- runtime substrate updates across `compose/`, `config-templates/`, `docs/`,
  `examples/`, `schemas/`, `scripts/`, and `generated/`, including the switch
  to canonical llama.cpp posture, diagnostic-spine contracts, antifragility
  receipt schemas, machine-fit fallback and tuning, and federated advisory
  seams
- runtime follow-through and operator surfaces under `.agents/`, `.github/`,
  `docs/routes/AUDIT.md`, `ROADMAP.md`, `QUESTBOOK.md`, `quests/`, `README.md`,
  `AGENTS.md`, `.agents/spark/`, and `tests/`, including quest-harvest installs,
  runtime closeout receipts, winner promotion, route-first ToS graph UI and
  curation overlays, OVMS text-lab lanes, and parity-safe source and deployed
  mirror checks

## [0.1.0] - 2026-04-01

First public baseline release of `abyss-stack` as the infrastructure substrate for the AoA / ToS ecosystem.

This changelog entry uses the release-prep merge date.

### Summary

- first public baseline release of `abyss-stack` as the repository that owns runtime, deployment, storage, lifecycle, security, and infrastructure glue beneath AoA and ToS
- the public baseline now includes Fedora-first deployment doctrine, source-checkout versus deployed-runtime path rules, rootless Podman lifecycle helpers, profile and preset composition, helper-service build contexts, and bounded federation/runtime seams
- this release keeps `abyss-stack` on the runtime layer without absorbing source-owned meaning from AoA layers or `Tree-of-Sophia`

### Added

- community-docs baseline established for this repository
- `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and `CONTRIBUTING.md`
- root runtime doctrine under `README.md`, `CHARTER.md`, `BOUNDARIES.md`, `ROADMAP.md`, and the current `docs/` architecture, deployment, runbook, path, preset, profile, reference-platform, machine-fit, and runtime-bench surfaces
- source-managed runtime helpers under `scripts/`, including layout, sync, bootstrap, lifecycle, doctor, render-truth, smoke, governed-run, host-facts, machine-fit, pilot, and federation-sync entrypoints
- public-safe config templates, helper-service contexts, schemas, and examples under `config-templates/`, `schemas/`, and `examples/`

### Validation

The baseline was verified through the then-current source, parity, and Python
compilation routes.

### Notes

- this release establishes the source-authored baseline for the runtime layer; deployed runtime state still becomes live only after sync into `/srv/AbyssOS/abyss-stack/Configs`
