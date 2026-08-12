# Validation

Run the paired source proof with the exact `aoa-sdk` checkout that owns
`AgentIncarnationBinding`:

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
  mechanics/governed-execution/parts/external-codex-agent/bind_external_actor_launch.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_mount_launcher.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_supervisor.py \
  mechanics/governed-execution/parts/external-codex-agent/install_external_codex_runtime.py \
  mechanics/governed-execution/parts/external-codex-agent/prepare_landing_study.py

python -m ruff check --no-cache \
  mechanics/governed-execution/parts/external-codex-agent

python -m pytest -q \
  mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_runtime_install.py

python scripts/validate_stack.py
python scripts/validate_decision_records.py
python scripts/generate_decision_indexes.py --check
python scripts/validate_nested_agents.py
```

The focused suite uses disposable Git repositories and a fake Codex-compatible
binary. It proves exact fixture admission plus separate owner-contour semantic
admission against pinned `aoa-agents` and `aoa-skills` schemas, a neutral
profile-bound specialized-environment release containing exact Python package
metadata, the packaged SDK Python root, and a clean tracked owner snapshot,
refusal of missing, drifted, or dirty specialized inputs, child environment
injection without user-site inheritance or pytest cache residue, and read-only
permission coordinates for those release roots; a neutral
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
pre-exec digest-drift refusal, and a real historical outer-bubblewrap plus inner
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
review-seed projections while refusing a replacement inode. Unicode/JSON-escaped
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
retaining the original baseline as the cumulative delta origin,
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
Codex 0.147 bubblewrap/private-PID selection with legacy fallback disabled,
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
Bash rcfile/init-file startup execution refusal,
hidden Git symbolic-ref, reflog, ref, and object mutation refusal with
read-only metadata inspection preserved,
GNU sed `--sandbox` enforcement, config-driven Git helper refusal,
sourced-shell refusal, Git alias/config-write/external-subcommand refusal, ambient
environment-assignment refusal, Git-invisible FIFO and Unix-socket refusal,
post-preflight full-manifest drift refusal, source-race refusal before
inference, final actor-manifest/delta tamper refusal,
provenance checks for all loaded `aoa_sdk` modules in the study preparer plus a
post-compilation persisted
path inventory, produced-artifact admission, source-evidence file/line
validation including a source scope wider than mutation scope, reserved
runtime final-manifest evidence with false-anchor refusal, signal-notified
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
only at the fixed upstream hop, and ambient/other MCPs are absent.

That suite does not prove the installed Codex binary, ChatGPT quota behavior,
Luna role performance, comparative net benefit, productive eval/stats/memo or
landing work, packaged four-owner compatibility, or live deployment. Those
require separate real-model and clean packaged-source receipts.
