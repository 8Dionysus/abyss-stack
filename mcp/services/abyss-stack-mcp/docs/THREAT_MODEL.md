# Threat model

## Protected claims

- a read caller cannot enumerate or prepare candidate/runtime effects;
- a candidate output cannot claim execution authority;
- stale or replaced evidence cannot silently authorize a plan;
- a compromised owner adapter cannot self-assert stack provenance;
- one credential cannot cross owner or policy contours.

## Controls

- a separate credential for each read and candidate process, alongside
  separate ports, tools, scopes, and client identities, with equal bearer
  values rejected after provisioning; an atomically published non-secret
  digest manifest is loaded beside only the selected contour credential, so
  every managed startup verifies both committed digests remain distinct and
  its own loaded bearer still matches its contour before binding a listener;
- explicit pair rotation only after both managed planes are observably stopped;
  it replaces both bearer values and the binding manifest without printing
  them, leaves restart and consumer refresh explicit, and any partial
  publication fails closed at the next startup manifest check;
- loopback-only HTTP with DNS-rebinding protection;
- loopback is transport locality, not caller identity: HTTP dispatch is still
  bound to the contour bearer client and exact scope; managed units deny all
  non-loopback IP traffic;
- a protocol-independent exact tool/effect allowlist with input/output byte
  limits, per-process concurrency and rate limits, bounded dispatch deadlines,
  cancellation propagation, and public-safe allow/deny/cancel receipts;
- policy receipts contain input/output digests rather than values, mark all
  returned content as untrusted data with no instruction authority, and never
  authorize runtime effects;
- explicit regular observation file with symlink rejection and a 2 MiB limit;
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
- fail-closed reprovisioning while either managed stack MCP plane is active,
  with lifetime shared source-projection and runtime service locks, exclusive
  provision locks, and a final stopped-state check before environment
  replacement;
- unit link/reload and runtime provisioning cannot be combined in one
  invocation; the standalone provisioner requires both units to be loaded from
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
- activation and restart reject `internal_effect` and `external_effect`
  subjects while their distinct threat, approval, egress, compensation, and
  rollback contracts are absent;
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

## Confused deputy

The server never proxies another MCP tool and never dispatches a plan. An
operator or later effect plane must revalidate the exact target, evidence,
approval, current snapshot, postcondition canary, and rollback route. Discovery
therefore cannot turn this service into a confused deputy for sibling
authority.

## Residual risk

A same-UID process that can read the deployed Secrets tree remains outside the
protection offered by bearer authentication. OS-user or container isolation is
required before any effect plane. No effect plane is admitted by this package.
Deadline cancellation cannot terminate an already-running Python worker
thread. Current dispatches are bounded, local, and non-effecting; an effect
plane must use cooperatively cancellable or process-isolated handlers before
admission.
