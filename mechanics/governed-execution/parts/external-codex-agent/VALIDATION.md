# Validation

Run the paired source proof with the exact `aoa-sdk` checkout that owns
`AgentIncarnationBinding`:

The focused `test_external_codex_landing_effect.py` suite validates the new
provider-neutral grant schema and admission seam without starting a process or
performing a landing effect. It covers the exact all-four landing-effect set,
absent and stale grants, pending review, artifact drift, wider effect scope,
contradictory target binding, exact Goal/holder/repository/target/review/return
admission, and preservation of the complete ten-effect runtime-wide forbidden
closure. Commit cases additionally prove that newly issued
`cached_index_v1` grants require the cached staged-diff digest, while an
`authenticated_legacy_v1` grant additionally requires independently
digest-verified migration evidence and a matching owner receipt resolved from
the release-bound owner migration catalog, bound to the exact grant,
repository, and manifest before a historical v1 manifest may omit it. A
caller-supplied receipt is never authoritative. The grant result is
admission evidence only; current command classification and profiles remain
external-effect-free.

```bash
AOA_SDK_SOURCE_ROOT=/absolute/path/to/aoa-sdk \
AOA_AGENTS_SOURCE_ROOT=/absolute/path/to/aoa-agents \
AOA_SKILLS_SOURCE_ROOT=/absolute/path/to/aoa-skills \
PYTHONPATH=/absolute/path/to/aoa-sdk/src \
python -m pytest -q \
  mechanics/governed-execution/parts/external-codex-agent/tests

PYTHONPATH=/absolute/path/to/aoa-sdk/src \
python -m py_compile \
  scripts/aoa-external-codex-agent \
  scripts/aoa-external-actor-bind \
  scripts/aoa-external-codex-incarnation \
  mechanics/governed-execution/parts/external-codex-agent/bind_external_actor_launch.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_landing_effect.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_nested_evidence.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_mount_launcher.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_supervisor.py \
  mechanics/governed-execution/parts/external-codex-agent/install_external_codex_runtime.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_return.py \
  mechanics/governed-execution/parts/external-codex-agent/goal_lifecycle_adapter.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_responsibility_movement.py \
  mechanics/governed-execution/parts/external-codex-agent/prepare_landing_study.py \
  mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py

python -m ruff check --no-cache \
  mechanics/governed-execution/parts/external-codex-agent

python -m pytest -q \
  mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_runtime_install.py

python scripts/validate_stack.py
python scripts/validate_decision_records.py
python scripts/generate_decision_indexes.py --check
python scripts/validate_nested_agents.py
```

## Incarnation-home projection and visible binding

The focused home suite covers the v2 manifest/schema binding, the
owner-authored capability-class registry and its explicit unknown path, default
projection of session continuity and actor tooling, deny-by-default ambient
operator-control and unknown entries, exact subject-bound operator grants,
canonical class policy enforcement, rejection of an operator-control policy
override and unsafe future shared-link tuple, schema-coherent denied future
vocabulary entries,
grant expiry and artifact drift, intentional same-subject grant reuse until
expiry, acceptance of mutable dynamic endpoint contents without target-content
binding, and cleanup of links left by the previous broad projection. The same
suite verifies that the visible holder retries the causal Kitty
ancestry/dedication handshake before publishing its holder receipt and fails
closed when the exact terminal binding is not ready. These tests prove source
behavior only; they do not prove installed-release parity, host
trust/admission, a live visible canary, app-server effect enforcement, wake
delivery, holder closure, owner acceptance, or Goal acceptance.

The F4 residual regressions also prove that duplicate future class IDs cannot
be represented in the registry schema because class IDs are object keys, and
that a shared operator-control entry is schema-invalid without its nested
`explicit_grant`. A forged grant projection with altered metadata may remain
descriptive-schema-valid, but manifest loading recomputes the exact
subject/entry/artifact relation and rejects it; this is the runtime admission
boundary, not evidence of trust admission or app-server enforcement.

The wake/return repair adds deterministic coverage for the explicit
holder-loss reentry packet: source duty/event digests, same-actor/session
continuity, replacement holder identity, and provenance drift are rejected
fail-closed. Return-route tests prove strict input-digest binding, including an
intervening valid-input mutation after route preflight and before delegated
dispatch, output-path non-aliasing, and delegation without Goal or terminal
selection. The holder tests also reject a rebound-shaped post-exec receipt when
its replacement provenance is missing. These checks still do not claim a live
app-server delivery, holder closure, semantic acceptance, or installed-release
parity.

The focused external-return tests cover the generic Goal lifecycle contour:
owner-resolved typed requests and decisions reject stale Goal/DAG/ownership
state before transport, and the same adapter executes both delegation pause
  and accepted-return activation through `thread/goal/get`, one native
`thread/goal/set`, and an authoritative read. The fixture receipt keeps
requested, accepted, executed, delivered, semantically accepted, and closed
claims separate and asserts that no turn or terminal transport is used. The
adapter also rejects mismatched decisions and replays an already desired
state through a read-only path. A mutating attempt persists its exact Goal
precondition and dispatch marker before transport, records the server proof
before receipt publication, and reconciles a proof-recorded ambiguous retry
through `thread/goal/get` without a second `thread/goal/set`. Receipt replay
revalidates the exact decision reference, transition frame, proof, and
response digests; executed receipt replay also requires the mutation attempt
sidecar, binds the authoritative result response to its digest and safe
summary, and rejects a receipt whose path identity is missing or changed. A
  concurrent SDK regression drives two callers through different durable
  attempt paths, and a CLI regression drives the same accepted request through
  different receipt paths. Both prove that the owner/idempotency-derived lock
  permits exactly one native Goal mutation while the other caller resolves the
  same proof-recorded attempt. A separate concurrency regression gives the same
  owner-bound Goal two accepted requests with different idempotency keys and
  proves the common Goal-identity lock permits exactly one native mutation. A
  physical-coordinate regression disables that wider Goal lock, races two
  different semantic requests against one attempt path, and proves one durable
  claim, one fail-closed loser, and one native set. An umask regression starts
  without `.local/state`, applies `0002`, and proves every newly created
  persistent-state parent is mode `0700`. A later-state-reversal regression proves that the
same idempotency key resolves that original attempt from its protected
semantic anchor and refuses a second mutation even through a different
receipt. A runtime-reset regression replaces the complete volatile lock root,
then proves that the persistent owner-state anchor still resolves the original
attempt and refuses a second mutation after state reversal. An already-desired
regression records `read_only_recorded`, reverses the Goal, retries through a
different receipt, and proves zero native sets. Additional regressions remove
the anchored sidecar and prove the surviving owner-state anchor is terminal,
and replace an otherwise valid replayed read-only response to prove the receipt
must match the exact recorded observation. Parameterized transport regressions
fail the first invocation during endpoint discovery and RPC setup, verify the
v2 anchor remains unstarted, then prove a retry persists one attempt and issues
exactly one native set. A dynamic-endpoint
regression additionally
returns different owner-proved app-server paths to the two callers and proves
that endpoint discovery remains inside the same stable semantic lock while the
attempt retains its historical endpoint evidence. Separate CLI regressions
rewrite the request and decision after the pre-read and prove both are
reasserted before dispatch with zero mutations; publication-boundary
regressions rewrite each artifact after the receipt write and prove the final
snapshot reassertion rejects it. Separate
legacy-pause regressions rewrite the owner after the pre-read and after proof
persistence, proving zero mutation in the first case and refusal to publish a
completed receipt in the second. Separate
programmatic regressions rewrite the owner after the precondition read and
after the authoritative post-read: the former proves no mutation is sent, and
the latter proves the persisted attempt remains bound to the original owner
bytes while receipt return fails closed.

The legacy external-return tests also cover the separate Goal pause contour:
an exact active owner-bound Goal uses the current public `thread/goal/set`
surface once, then proves the returned identity, status, request, precondition,
and fresh post-read before a receipt is published. Non-active Goals are refused
without a lifecycle mutation, and a completed pause receipt replays without a
second app-server call. Concurrent legacy callers using different receipt
paths serialize on the qualified Goal identity and issue exactly one native
mutation. The suite also forces dispatch-marker, transition-proof,
and receipt publication failure at their respective boundaries and verifies
that a pre-send reservation fails closed while a matching post-send dispatch
marker is reconciled through a read-only Goal read without a second
`thread/goal/set`.
Companion cases prove that an active observation after dispatch fails closed, a
paused observation through a replacement app-server endpoint fails closed, a
paused observation without the marker or proof fails closed, and incomplete or
copied completed receipts fail closed. The fixture asserts that pause does not
use turn delivery, terminal input, process identity, holder closure, or wake
evidence. The reservation fixture validates the initial, prepared, pre-send,
and post-send reservation states against the separate
`abyss_stack_external_codex_pause_reservation_v1` schema, while completed
evidence remains validated by the pause-receipt schema. The current public
Codex app-server can now serve the live fresh `active_to_paused` canary through
its public Goal set method; no source test double is a live canary claim.

The responsibility-movement tests prove the required branch independently:
the compiled obligation and exact handoff digest are carried through a
one-shot observation; a live process plus the real
`cannot_connect_to_codex_app_server` transport failure is classified as
deadline stasis because no lifecycle transition was observed; the typed event
and review wake bind the exact return owner and preserve the stop line. Adding
the matching `returning -> terminal` transition changes the result to
`progressing` and suppresses the wake, proving the causal dependency. Cost
over-budget and pre-deadline cases schedule only one bounded observation, and
hook-screen evidence is rejected by schema. No external canary, Goal
acceptance, or host trust-admission success is claimed by this observer.

The deterministic suite separates transport sentinels from unrelated semantic
cases without exposing a runtime bypass. Fixtures selecting
`exact_preflight=True` execute the production path for executable pathname
replacement, nested Codex sandbox, missing role-scoped MCP credentials, and the
complete preflight/start/worker lifecycle. Probe-group tests directly exercise
overlap, timeout cleanup, and completed-sibling descendant cleanup. Other
lifecycle, report, evidence, and authority cases bind a successful
contract-shaped `_codex_preflight` double to the test runtime instance only.
Because the worker is forked, the double traverses the same admission and worker
revalidation call sites; second-return drift tests still prove the repetition.
No launch field, profile, environment variable, installed wrapper, or
production source path can select this test-only double. Any test whose verdict
depends on live preflight must use the exact fixture path.

Runtime schema loading retains a separate fail-closed optimization. Every load
still reads the named file, parses its current bytes into a fresh mapping, and
runs the requested value validation. Only a successful Draft 2020-12
meta-validation is memoized, keyed by the complete schema bytes, for at most 64
schemas no larger than 512 KiB. Changed bytes are a cache miss, invalid schemas
are rejected again because exceptions are not cached, and larger schemas always
take the uncached meta-validation path. The focused cache regression proves all
of those boundaries, including that callers never receive a shared mutable
schema object.

The focused suite uses disposable Git repositories and a fake Codex-compatible
binary. It proves exact fixture admission plus separate owner-contour semantic
admission against pinned `aoa-agents` and `aoa-skills` schemas, a neutral
profile-bound specialized-environment release containing exact Python package
metadata, the packaged SDK Python root, and a clean tracked owner snapshot,
refusal of missing, drifted, or dirty specialized inputs, child environment
injection without user-site inheritance, attempt-local `PYTHONPYCACHEPREFIX`
residue, or pytest cache residue—including explicit `py_compile`, ordinary
imports, and resume-separated scratch coordinates across generic and landing
workspace-write profiles—and read-only permission coordinates for those release
roots. It also proves that admission preflight does not create or receive an
attempt prefix through `state_root`, while every real start/resume path remains
scratch-bound across the admitted workspace-write profiles. The focused
runtime-invariant-closure tests additionally compare literal, Unicode-escaped,
slash-escaped, mixed, and nested UTF-8 source text while preserving unrelated
backslash/newline bytes. A neutral
non-starting binder, accepted responsibility transfer with two exact holders,
a ready task-local DAG and exact domain procedure refs, a distinct OS process,
structured events and output, no built-in multi-agent flag, byte-aware
read-only drift containment including every tracked byte,
assume-unchanged/skip-worktree mutations, and ignored bytes,
tracked-submodule, untracked-embedded-repository, and outward-symlink refusal, a foreground `run-to-terminal` lifecycle for transient cgroup launchers without execution
ceilings, secret-shaped ignored input refusal including conventional
credential-config dotfiles before hashing or direct reads, complete runtime-wide forbidden-set admission plus subset-resistant
terminal classification, direct secret-path encoder classification, exact-open-inode
Codex preflight and inference execution across a pathname replacement plus
pre-exec digest-drift refusal, bounded process-isolated overlap of independent
preflight probes with exact timeout cleanup and no shared controller thread,
and a real historical outer-bubblewrap plus inner
named Codex-sandbox preflight command. The mount-wrapper and mount-launcher
checks also prove the descriptor-bound inference contour. The projection slice
proves an admitted Git baseline is copied through open descriptors, receives a
source-independent private `.git` body with equivalent status/diff, and is
mounted from its exact open inode at the stable child coordinate. Source
manifests are checked before and after materialization, source-parent replacement
cannot expose source config to the actor, a source race fails without an orphan
projection, projection-local Git packing disables promisor lazy fetches before
actor containment, and a post-publication target swap cannot become the durable
actor baseline. Publication is relative to a pinned parent descriptor, its baseline
comes from the retained staging inode, uses non-replacing rename, and cleans the
exact committed inode after an injected post-rename failure for both source and
review-seed projections while refusing a replacement inode. Admitted
shallow-source tests preserve only necessary commit boundaries, reject malformed
or forged boundary metadata, and pass strict full fsck. Terminal
review-state tests seal the actor tree before lock release, tolerate a benign
post-closeout index refresh, replay repeated issuance idempotently, and reject
tampered seal objects or cross-session materialization. Unicode/JSON-escaped
source coordinates are removed from mapping keys, values, arbitrary text, and
model-facing control views by schema-validated actor input envelopes. Tests
cover mixed/case-varied/nested escapes, escaped slashes, surrogate pairs,
invalid-UTF-8 binary shadows, and bounded-depth rejection; key collisions fail closed, controller originals are denied, and system minimal-read roots
are not valid source locations. A host projection pathname replacement after open is detected
at closeout while the child continues on the original inode;
create/modify/delete/binary/mode/symlink changes yield a canonical actor
delta while the source remains unchanged. It also proves independent
same-source sessions use distinct projections, rather than treating a source
flock as a rename defense,
exclusive same-projection active-attempt admission across distinct
session identities, wrapped effect-family observation, exact validation-claim
binding to final workspace bytes, bounded recovery from transient regular-file
inventory and disappearing-directory enumeration races with immediate refusal
of nontransient projection errors,
authority-blocked failure closeout when the
final manifest is unobservable or a dying worker leaves read-only/out-of-scope
projection drift, final-lock rejection of changed review seed, actor
manifest/delta, and writer/reviewer summon request/schema bytes, strict
`landing_review` admission/export binding, streaming rejection of an unterminated
oversized protocol record, review-gate enforcement, TERM-resistant and unexpected-worker-death
cleanup including a detached `setsid` descendant, high token/turn usage
measurement without truncation, durable interrupt/resume on one thread,
strict recovery of a complete main-session event append before state save,
semantic replay of a lost thread, usage, turn, and indirect command state save,
authority-blocked interruption after a forbidden command was durably observed
at `item.started`, attached shell-separator effect recognition,
authority-blocked worker-death closeout after a recovered command, retry of
a durable attempt-free `prepared` session after launch failure, an exact
pre-fork child launch gate, and refusal to release a historical mount gate after a parent
termination signal or supervisor-endpoint EOF, using a bubblewrap-retained peer
and killing the complete blocked wrapper test tree before closing the supervisor
endpoint,
incremental recovery and observation of cumulative event history without an
aggregate control-file read, recovery of an exact atomically written terminal
result when the final state save is lost without fabricating worker death,
partial-usage classification when interruption precedes Codex usage emission,
immutable preservation of the interrupted receipt and its complete evidence
closure across ordinary resume, including multiple terminal revisions within
one recovered attempt,
digest-bound continuation evidence materialization without arbitrary host-path
reads, including controller-original and actor-safe copies, session-local
`immutable:` schema expansion, prompt content withholding, all-entry
prevalidation, and fail-closed digest mismatch before inference,
workspace-write continuation from the exact preceding actor final tree while
retaining the original baseline as the cumulative content-delta origin while
binding private-Git observation to the exact preceding actor final manifest,
and rejecting a new private-Git drift during the resumed attempt,
runtime-owned actor projection as the Codex target/cwd for both read-only and
workspace-write actors, with the source checkout outside actor writes, fixed
validation argv bound to that projection, and source-path exclusion from
cwd/prompt/argv,
session-local exact task/incarnation constraints with tamper refusal,
immutable-input evidence identities constrained before structured output,
idempotent exact duplicate evidence with raw-report preservation and typed
semantic failure messages,
digest-bound same-thread recovery from one unchanged read-only reviewer
identity typo and from one authority-safe bounded writer model-report error,
while preserving each failed result and refusing any writer path widening,
typed pre-turn provider-capacity failure plus exact same-role/thread recovery,
legacy generic-code recovery only from the result-bound structured terminal
event pair, and refusal of an ordinary process failure through that route,
exact terminal validation-suffix admission when an earlier fixed receipt sees
transient command-sandbox state, while post-validation mutation still fails,
canonical non-starting reviewer preparation with controller-owned immutable
copies and stable forwarded input IDs, reviewer operation after the historical
source checkout disappears or an historical ancestor is retargeted,
owner-contour review-input compatibility from an exact durable source baseline
and selected SDK v4 schema without historical writer mutation, changed-baseline
refusal, and final locked equality of the derived writer and active reviewer
schema copies, explicit owner-only mixed typed-request/generic-decision
compatibility with task/snapshot/continuation binding, and workspace-root `.`
scope parity between writer execution and reviewer preparation,
single-step owner plans whose active writer task/request step is rebound to the
exact selected read-only reviewer without rewriting unrelated DAG steps,
historical writer runtime-profile drift with the new reviewer bound to the
current admitted profile while the writer evidence stays immutable,
nonterminal/stale/foreign review-seed refusal,
an explicit transport-study or owner-contour workspace-write coder to a
plan-bound read-only reviewer transition with a
post-write actor manifest/delta and reviewed A2A return, exact review-input-to-
writer-final-manifest and writer-delta digest binding, exact projection-seed
envelope ownership and terminal-result binding, mandatory seed presence in
reviewed A2A export, result-v2 mandatory successful
projection provenance with legacy-v1 read compatibility,
reuse on reviewer preparation, reviewer lock retention through durable A2A
export,
reviewer-result race refusal, role-first owner-contour writer/reviewer A2A
admission with distinct threads, exact writer task/result/report/output closure,
SDK request/schema equality, read-only zero-delta review, and refusal when the
writer report is absent, wrapper-delimiter effect observation,
non-replacing owner-generation anchoring outside the session tree, rejection of
a coordinated launch/request/state/result v4-to-v3 rewrite, refusal to reopen
legacy migration after deleting that anchor, release-catalog-bound and
digest-pinned legacy-v3 migration, refusal of catalog-bearing ordinary install
and activation, artifact-admitted catalog activation, unanchored-legacy
refusal, recovery of a pre-attempt legacy prepared state, and exact retry after
a current generation anchor or its prepared event was published but first state
was not,
unclassified non-validation interpreter indirection with exact fixed-validation
exemption, fail-closed `env --split-string` handling, value-aware `timeout`
wrapper parsing, opaque process-launch-wrapper refusal,
attached-redirection observation, fail-closed shell nesting at the inspection
limit, command/backtick/process-substitution refusal, opaque build/package/test
runner refusal, active parameter/glob/brace/tilde-expansion refusal with quoted
literal preservation, Bash extglob refusal, fixed-system-`PATH` executable
allowlisting with unadmitted bare-name refusal, direct workspace/non-system
executable refusal including shell-name impersonation, opaque AWK program-body
refusal, isolated non-writable shell `HOME` with ambient-profile refusal,
ripgrep preprocessor/hostname/decompressor dispatch refusal with ordinary
search preserved and ambient ripgrep configuration disabled, clean CLI re-exec
with the upstream MCP bearer carried only through a bounded sealed descriptor,
absence of the bearer name and value from live controller, worker, supervisor,
and Codex exec-time environments, actor `/proc` denial, attempt-local MCP bearer
relay with the upstream credential absent from Codex,
incremental streaming relay and active-connection termination before finalize,
Codex 0.148 bubblewrap/private-PID selection with legacy fallback disabled,
live Codex process-environment proof that the upstream bearer name and value
are absent without claiming path-alias inference from cwd-less events,
signature-format
revision-walker refusal, and fixed false OpenPGP/X.509/SSH verifier coordinates,
GNU sort compression-program dispatch refusal with ordinary sort preserved,
hidden Git ref mutation refusal with ordinary ref inspection preserved,
credential-bearing Git config read refusal alongside config-write refusal,
argument-role distinction between a Git-config search literal and an actual
file operand, all multi-file, explicit-pattern, GNU-abbreviated pattern and pattern-file,
and jq file-loading reader forms,
attached generic-mutator destination options, existing and
reserved config-lock masking, complete masking of both coordinates of a
bind-mounted repository config inode, preservation of reftable repository
structure, case-handling status semantics, normalization of local rename-display
preferences across owner and masked probes, exact-workspace preservation and
redirect refusal for `core.worktree`, namespace-private reservation of absent
config coordinates with no host `.git` mutation and a still-working owner
`git config`,
credential-bearing Git remote URL refusal with name listing preserved,
jq env/$ENV secret-access refusal with ordinary data transforms preserved,
abbreviated Git cat-file filter/textconv and hash-object path refusal,
hash-object filter-enabling refusal with exact no-filter hashing preserved,
signature-backed for-each-ref and revision-walker verifier refusal,
controller and model Git promisor lazy-fetch helper suppression,
unconditional zsh startup refusal, Bash login/interactive/rcfile/init-file
startup execution refusal, find output-action Git-metadata mutation refusal,
hidden Git symbolic-ref, reflog, ref, and object mutation refusal with
read-only metadata inspection preserved,
GNU sed `--sandbox` enforcement, config-driven Git helper refusal,
sourced-shell refusal, Git alias/config-write/external-subcommand refusal, ambient
environment-assignment refusal, direct and option-attached system-utility
secret-coordinate classification, Git-invisible FIFO and Unix-socket refusal,
post-preflight full-manifest drift refusal, source-race refusal before
inference, final actor-manifest/delta tamper refusal,
provenance checks for all loaded `aoa_sdk` modules in the study preparer plus a
post-compilation persisted
path inventory, produced-artifact admission, source-evidence file/line
validation including a source scope wider than mutation scope, controller-issued
stable zero-delta/private-Git runtime evidence refs, reserved runtime
final-manifest evidence with false-anchor refusal, pre-inference
digest-bound nested evidence closure across producer task/result/report/delta,
same-name digest-collision disambiguation, historical source excerpts,
validation observations, line/member/content-entry/output manifest anchors,
partial-producer model-only fallback, ambiguity/drift refusal, and
runtime namespace-entry citation, signal-notified
steady-state supervisor waiting, status-selected
wake binding, failed-reviewer A2A refusal, absence of an outer namespace that
would conflict with Codex sandboxing (the filesystem boundary uses rootless
user+mount namespaces but adds no PID or network namespace), native
nested-repository Git behavior,
and a separately bound review/A2A export.
Compatibility proof also loads completed pre-change v1/v2 states for status and
terminal-result recovery, without granting them a new inference attempt when a
safe v3 projection is absent. A Python 3.11 launcher regression proves namespace
setup calls libc's `unshare` syscall path and never depends on `os.unshare`.
It also proves parent obligation admission, durable pre-inference `yielding`
state, preservation and retry beyond a partial yield attempt, recovery of a
complete yield event without a second inference, a completed yield turn followed
by durable waiting, canonical child state/result/event receipt binding, rejection
of a standalone result, child-session locking through the durable parent event
admission, recovery of a valid event append that preceded its
state save, recovery of the completed semantic turn when its event preceded
the state save, locked status observation, re-entry recovery after a crash
before turn materialization, completed-turn recovery without a second
inference, immutable child-attempt admission independent of later canonical
child-result changes, pre-inference parent-turn tool disabling and isolated
non-writable parent `HOME`, rejection of tool events in parent turns, false-event
filtering with no second parent turn, and exact-thread parent re-entry with a
distilled return. The fake Codex fixture exercises both filtered and wake branches;
separate live receipts are required for the installed product surface. The
installer suite additionally proves that index-hidden packaged source and
ignored files entering the packaged SDK require explicit dirty-source
admission, and that activation plus status reject a non-CPython executable or
an interpreter shim whose eventual delegate is not bound. A synchronized host
release-directory rename and replacement after wrapper verification proves
that a deferred import still reads the namespace-private verified snapshot.
The installer also proves that each launcher is a static x86_64 ELF without
`PT_INTERP`, that an ambient constructor-bearing `LD_PRELOAD` cannot run before
the wrapper filters loader state, that a same-UID replacement at the former
adjacent companion coordinate is never executed, and that otherwise-valid
active-record byte drift is rejected by the digest embedded in the launcher.
Wrapper execution under writable directory modes
is also proven not to create bytecode inside the immutable release. A
clean-checkout race between initial posture capture and release
hashing is proven to fail before wrapper or active-receipt publication. The
suite also rejects an unmanifested importable file from an otherwise
content-addressed release. It separately proves that `stage` materializes no
active record or stable wrapper, that `activate-admitted` binds a fresh exact
host trust-gate result to the staged source and release-manifest aggregate, and
that a mismatched admitted subject fails before publication.

It also proves role-scoped MCP argv isolation: the selected AoA server alone is
configured through an attempt-local relay, its exact upstream token is required
but absent from Codex argv, environment, and model shell, the relay injects it
only at the fixed upstream hop, the runtime explicitly enables the pinned
Codex modern-MCP feature, the relay preserves exact modern MCP version
`2026-07-28` while rejecting missing or stale client protocol headers before
any upstream request, and ambient/other
MCPs are absent.

That suite does not prove the installed Codex binary, ChatGPT quota behavior,
Luna role performance, comparative net benefit, productive eval/stats/memo or
landing work, packaged four-owner compatibility, or live deployment. Those
require separate real-model and clean packaged-source receipts.

The visible-incarnation tests additionally prove that a direct responsibility
holder writes a non-replacing lifecycle receipt before `exec`, records
post-exec argv (including shebang interpreter shape), its process parent and
first detached Kitty window, rejects sibling Kitty children, and keeps holder
identity separate from runtime proof-actor identity. The canonical detached
route allocates a unique private socket, persists the Goal/actor/session,
process/start-tick, window, TTY, title, runtime-root, and closeout binding, and
starts Kitty in socket-only mode. Focused observability tests prove safe
allowlist projection from an environment-bearing Kitty payload, read-only
status with unchanged socket permissions, PID/start-tick reuse protection,
stale/missing state, and exact directed-input targeting; no status output
contains environment, command line, token, or credential fields. The installed
`join` route proves a returned responsibility without wake delivery and creates
typed `join_completed` authorization; the wake route creates the parallel
`wake_delivered` authorization. The installed `close` route accepts either
typed authorization (or the legacy wake receipt), binds the exact holder
receipt digest, PIDs, required terminal action, and reserved closure path; it
pins and rechecks the validated handoff before publishing join or wake
authority, records authorization/evidence digests in v2 reservations, and
replays completed v1 closure receipts only through the matching legacy wake
route. It rechecks PID/start-ticks, argv, process parent, Kitty
window/dedication, reserves before signaling, and uses pidfd TERM. A live
visible trial must separately prove the installed release, the corresponding
return evidence, holder disappearance, final Kitty disappearance, unrelated-
terminal preservation, and the resulting closure receipt. The companion first
detached Kitty window, rejects sibling Kitty children, rejects receipt
binding for detached/non-dedicated launches, and keeps holder identity separate
from runtime proof-actor identity. The companion
regression additionally proves that an ELF launched from an anonymous memfd
cannot discover its adjacent code-mode host, while the repaired private
package coordinate exposes only the digest-bound companion beside the exact
Codex ELF and permits one successful code-mode probe.
