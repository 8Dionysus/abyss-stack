# Threat model

## Protected claims

- a read caller cannot enumerate or prepare candidate/runtime effects;
- a candidate output cannot claim execution authority;
- stale or replaced evidence cannot silently authorize a plan;
- a compromised owner adapter cannot self-assert stack provenance;
- one credential cannot cross owner or policy contours.
- a host receipt cannot be confused with an owner result or SDK transition
  verdict.
- the internal-effect credential cannot select another unit, action, tool, or
  lasting applied state;
- a denied or incomplete effect attempt cannot disappear without a receipt.

## Controls

- a separate credential for each read, candidate, and internal-effect process, alongside
  separate ports, tools, scopes, and client identities, with equal bearer
  values rejected after provisioning; an atomically published non-secret
  digest manifest is loaded beside only the selected contour credential, so
  every managed startup verifies all three committed digests remain distinct and
  its own loaded bearer still matches its contour before binding a listener;
- explicit three-credential rotation only after all managed planes are observably stopped;
  it replaces all bearer values and the binding manifest without printing
  them, leaves restart and consumer refresh explicit, and any partial
  publication fails closed at the next startup manifest check;
- loopback-only HTTP with DNS-rebinding protection;
- loopback is transport locality, not caller identity: HTTP dispatch is still
  bound to the contour bearer client and exact scope; managed units deny all
  non-loopback IP traffic;
- a protocol-independent exact tool/effect allowlist with input/output byte
  limits, per-process concurrency and rate limits, bounded dispatch deadlines,
  cancellation propagation, and public-safe allow/deny/cancel receipts;
- a separate port-`5439` internal-effect process with one tool, one
  `apply_runtime` class, one literal systemd unit, its own bearer and scope, a
  process-isolated worker, a 120-second bound, and no generic shell, target,
  action, or external-network parameter;
- staged plan and approval artifacts are private regular mode-`0600` files
  below a mode-`0700` effect root; the approval is content-addressed, expiring,
  human-issued, and bound to the plan and idempotency key;
- the approval names the one fixed internal-effect principal, while HTTP auth
  binds the distinct bearer to that exact client identity and scope; read or
  candidate principals therefore cannot replay the approval;
- a process-wide file lock serializes execution and a private persistent
  attempt journal permits at most one new pilot start per minute; an
  idempotency receipt replays an existing success without repeating effects;
- immediately before mutation the executor rechecks the observation digest,
  freshness, source/package/deploy identity, unit, and exact live systemd
  process identity, then persists a pre-effect receipt;
- any pre-effect rejection writes a content-addressed denial receipt containing
  only a request digest and bounded reason code; any failure after the first
  restart attempt writes a recovery receipt with the actual rollback and
  post-canary state;
- after every first restart attempt the worker attempts the exact restart again
  as restoration; success requires distinct pre/post/post-rollback process
  identities plus authenticated post-effect and post-rollback canaries;
- policy receipts contain input/output digests rather than values, mark all
  returned content as untrusted data with no instruction authority, and never
  authorize runtime effects;
- managed receipts are synchronously appended to distinct read/candidate
  mode-`0600` canonical-JSONL hash chains before a decision is returned;
  startup validates the full bounded chain, sequence, owner/policy contour,
  receipt and record digests, secret screening, file type, permissions, and
  partial-tail state; each hardened unit receives an exact write path only for
  its own journal and cannot access the other contour's file;
- explicit regular observation file with symlink rejection and a 2 MiB limit;
- an atomic observation producer with regular-file and symlink checks for every
  input and output, content-address verification of both the latest deployment
  receipt and its immutable record, a committed unique target catalog, a
  private output directory, and no credential or endpoint-probe access;
- owner-issued overlay checks for every usable source, endpoint, freshness, and
  canary claim, while Pydantic subject validation retains proof, acceptance,
  and rollback issuer checks;
- a separate authenticated read canary that selects only a committed target,
  derives one exact owner credential filename, refuses symlinked or
  group/world-readable credentials, requires a current-user-owned mode-`0600`
  non-symlink Ed25519 private key, never serializes result values, and emits
  only an independently attested content-addressed mode-`0600` receipt,
  result artifact, and typed one-subject overlay;
- downstream attribution of a capture to `abyss-stack` requires verification
  of both receipt and result attestations against an independently pinned
  public key; content addresses, caller-supplied keys, issuer strings, and
  matching hashes are not issuer authentication;
- canary call success remains distinct from owner-specific grounding, while
  its claim ceiling excludes owner freshness, central proof, acceptance,
  admission, rollback, unit effects, and consumer configuration;
- transitional shared-bearer processes are excluded rather than assigned fake
  per-owner credential classes;
- strict input and output models with unknown fields denied;
- secret-like material rejected before validation or response;
- URI-like references, including scheme-relative forms, reject
  credential-bearing userinfo and forbidden path/query/fragment keys before
  validation or response; unparseable URI-like values fail closed, bounded
  recursive decoding covers nested parameters, and credential-key tokenization
  catches namespaced separator/camel-case forms plus concatenated recognized
  provider/consumer, passphrase, and credential-attribute boundaries, including
  exact `credential`/`credentials` and unambiguous compound credentials such
  as `secret_access_key`, plus bounded AWS presign keys, without
  treating arbitrary word substrings as credentials; structurally valid compact JWT and
  PEM private-key checks cover embedded material, Basic/Bearer checks normalize
  leading whitespace, and bounded provider-token patterns are scanned
  throughout values for the standard OpenAI, GitHub, and GitLab families;
- exact targets require at least one non-whitespace character;
- exact observation digest and short expiry for candidate plans;
- exact artifact-hashed runtime dependency closure, bound with deployed source
  into the managed-environment identity and installed only from a private
  digest-matched source snapshot, with the installed files, symlink targets,
  and fully resolved interpreter bytes rehashed against a recorded
  runtime-content digest before any reuse;
  generated entry-point shebangs are rebound to the stable publication path
  before that digest is recorded and the staged environment is renamed;
- fail-closed reprovisioning while any managed stack MCP plane is active,
  with lifetime shared source-projection and runtime service locks, exclusive
  provision locks, and a final stopped-state check before environment
  replacement;
- unit link/reload and runtime provisioning cannot be combined in one
  invocation; the standalone provisioner requires all three units to be loaded from
  their expected managed fragments with user systemd's effective lock-aware
  `ExecStart`; MCP Configs sync and runtime provisioning share an exclusive
  source-projection lock from their first mutation/read through publication,
  and deployed source is rehashed before the runtime marker/swap;
- each managed launch independently recomputes the deployed source-and-lock
  identity and measured runtime-content digest, including resolved interpreter
  bytes, then repeats that verification after taking shared source-projection
  and runtime locks that remain held across `exec` and for the process
  lifetime; sync, provisioning, and launch therefore cannot cross the verified
  snapshot, and the unit remains inactive on drift rather than trusting
  executable presence alone;
- sync plans verify both the observed source revision and source-tree digest
  before mutation; sync/deploy plans bind an expected future deployed-tree
  digest instead of reusing the pre-action observation, and rollback denial
  binds registry ID and digest together;
- structured allowlisted plan actions with no free-form command;
- active processes require an observed process identity rather than a bare
  boolean;
- restart candidates require an already active process, preventing restart from
  becoming an activation-gate bypass for an inactive unit; they also require
  and carry usable central-proof and current-canary evidence, with the proof
  bound to the exact source, package, deploy, process, server schema,
  compatible consumer registration, canary route, and receipt used by the
  plan, and the selected consumer evidence copied into the candidate;
- activation requires a passed central-proof verdict issued by `proof_owner`
  and bound to the current source revision and tree digest, package, deployed
  revision and tree digest, running process identity, schema, consumer, and
  exact canary route and receipt;
- generic candidate activation and restart continue to reject
  `internal_effect` and `external_effect` subjects. The D-0106 executor consumes
  only an exact read-subject restart candidate under its separate approval and
  rollback contract;
- activation requires acceptance-owner evidence bound to the exact source
  revision and package digest, and carries that expiring receipt into the
  candidate;
- required evidence timestamps cannot postdate the observation snapshot beyond
  the bounded clock-skew allowance;
- candidate causality and evidence expansion use only the exact
  proof-selected or last-known-good consumer, while candidate result freshness
  folds every copied plan link together with the subject freshness envelope;
- every step-relevant named deploy, consumer-registration, proof, acceptance,
  canary, or rollback target must equal a contained evidence identity that the
  candidate copies and expiry-bounds, including an absent current consumer
  selected for registration restoration; the proof and acceptance identities
  must also be issued by their respective declared owners rather than relying
  on a separate decoy receipt from that owner;
- read catalog and inspection use the earlier wall-clock/snapshot bound and
  downgrade a causally future observation envelope, link, freshness timestamp,
  or nested evidence ref to `blocked`;
- an expired observation envelope downgrades result metadata and each derived
  catalog/freshness/drift state to at least `stale_readable`;
- inspection preserves the raw owner link state while exposing its derived
  effective state and folding the selected view's link state into result
  freshness metadata;
- central proof cannot predate the canary evidence it names, and conflicting
  duplicate evidence timestamps are rejected before deduplication;
- rollback-required links need explicit unexpired evidence and cannot fail late
  through candidate-model validation;
- rollback readiness requires a typed proof target equal to the complete
  last-known-good restoration contour, including its distinct canary route and
  receipt; the rollback plan runs that proven canary and carries the usable
  rollback proof rather than depending on current-deployment canary evidence
  that may be failed, blocked, or expired;
- server-side read-subject filtering before catalog result construction and
  higher-policy inspection rejection before observation loading;
- server-side policy checks independent of MCP annotations or model behavior;
- the provisioner and managed units clear ambient Python import roots and use
  isolated interpreter mode, preventing inherited shell or user-manager
  `PYTHONPATH`/`PYTHONHOME` from shadowing the measured venv closure; managed
  launches also pass `-B` explicitly so isolated-mode environment filtering
  cannot re-enable bytecode writes into that measured closure.
- successful canary payloads are secret-screened, size-bounded, written only
  to private content-addressed result artifacts, and explicitly marked
  untrusted with no instruction authority; an artifact is never treated as
  owner grounding without a separately issued owner review.
- cross-organ host inputs, snapshots, receipts, and current records are bounded,
  secret-screened, non-symlink private files; writes are serialized by a
  mode-`0600` host lock, snapshots and receipts are immutable, and the read
  contour rechecks record plus snapshot digests before returning a bounded
  inspection;
- every cross-organ advance delegates the full transition to one explicit
  `aoa-sdk` command and requires SDK validation stop-lines. The stack issues
  the host receipt but never calls an owner tool. The candidate MCP process is
  denied the orchestration tree entirely.

## Confused deputy

The read and candidate servers never proxy another MCP tool or dispatch a
plan. The effect server accepts IDs only and independently revalidates the
exact target, evidence, approval, current snapshot, postcondition canary, and
rollback route. It cannot receive another unit, action, executable, endpoint,
or owner-tool name. Discovery therefore cannot turn this service into a
confused deputy for sibling authority.

## Residual risk

A same-UID process that can read the deployed Secrets tree remains outside the
protection offered by bearer authentication. Stronger OS-user or container
isolation remains desirable for broader effects. The admitted pilot therefore
has only the exact user-level read-service restart authority and no persistent
applied state or external effect.
Caller cancellation does not abort restoration midway: the server waits the
bounded worker window for the process-isolated executor to finish. If the
worker exceeds that bound the process group is terminated, and live operator
recovery plus the persisted pre-effect/recovery evidence becomes mandatory.
The journal hash chain is tamper-evident, not externally notarized. A same-UID
actor can still rewrite the file and recompute a replacement chain while the
service is stopped. External anchoring belongs to a later proof/evidence
handoff. The 32 MiB per-contour bound fails closed at capacity; no automatic
rotation or deletion policy exists yet, so archival requires a stopped-plane,
reviewed continuity handoff.
