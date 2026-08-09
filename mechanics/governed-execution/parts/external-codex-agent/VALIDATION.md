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
non-starting binder, accepted responsibility transfer with two exact holders,
a ready task-local DAG and exact domain procedure refs, a distinct OS process,
structured events and output, no built-in multi-agent flag, byte-aware
read-only drift containment including every tracked byte,
assume-unchanged/skip-worktree mutations, and ignored bytes,
tracked-submodule, untracked-embedded-repository, and outward-symlink refusal, a foreground `run-to-terminal` lifecycle for transient cgroup launchers without execution
ceilings, secret-shaped ignored
input refusal, complete runtime-wide forbidden-set admission plus subset-resistant
terminal classification, direct secret-path encoder classification, exact-open-inode
Codex preflight and inference execution across a pathname replacement plus
pre-exec digest-drift refusal,
exclusive same-workspace active-attempt admission across distinct
session identities, wrapped effect-family observation, exact validation-claim
binding to final workspace bytes, authority-blocked failure closeout when the
final manifest is unobservable, streaming rejection of an unterminated
oversized protocol record, review-gate enforcement, TERM-resistant and unexpected-worker-death
cleanup including a detached `setsid` descendant, high token/turn usage
measurement without truncation, durable interrupt/resume on one thread,
strict recovery of a complete main-session event append before state save,
semantic replay of a lost thread, usage, turn, and indirect command state save,
authority-blocked interruption after a forbidden command was durably observed
at `item.started`, attached shell-separator effect recognition,
authority-blocked worker-death closeout after a recovered command, retry of
a durable attempt-free `prepared` session after launch failure, and an exact
pre-fork child launch gate,
incremental recovery and observation of cumulative event history without an
aggregate control-file read, recovery of an exact atomically written terminal
result when the final state save is lost without fabricating worker death,
partial-usage classification when interruption precedes Codex usage emission,
immutable preservation of the interrupted receipt and its complete evidence
closure across ordinary resume, including multiple terminal revisions within
one recovered attempt,
read-only target projection through a separately recorded attempt-local Codex
execution root and temp area, with the target checkout outside writable roots,
session-local exact task/incarnation constraints with tamper refusal,
immutable-input evidence identities constrained before structured output,
idempotent exact duplicate evidence with raw-report preservation and typed
semantic failure messages,
digest-bound same-thread recovery from one unchanged read-only reviewer
identity typo while preserving the failed result,
canonical non-starting reviewer preparation with stable forwarded input IDs,
an explicit workspace-write coder to read-only reviewer transition with a
post-write manifest and reviewed A2A return, exact review-input-to-writer-final
manifest binding, reviewer lock retention through durable A2A export,
reviewer-result race refusal, wrapper-delimiter effect observation,
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
GNU sed `--sandbox` enforcement, config-driven Git helper refusal,
sourced-shell refusal, Git alias/config-write/external-subcommand refusal, ambient
environment-assignment refusal, Git-invisible FIFO and Unix-socket refusal,
post-preflight full-manifest drift refusal, final-manifest tamper refusal,
provenance checks for all loaded `aoa_sdk` modules in the study preparer plus a
post-compilation persisted
path inventory, produced-artifact admission, source-evidence file/line
validation including a source scope wider than mutation scope, reserved
runtime final-manifest evidence with false-anchor refusal, signal-notified
steady-state supervisor waiting, status-selected
wake binding, failed-reviewer A2A refusal, absence of an outer namespace that
would conflict with Codex sandboxing, and a separately bound review/A2A export.
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
child-result changes, rejection of tool events in parent turns, false-event
filtering with no second parent turn, and exact-thread parent re-entry with a
distilled return. The fake Codex fixture exercises both filtered and wake branches;
separate live receipts are required for the installed product surface. The
installer suite additionally proves that index-hidden packaged source and
ignored files entering the packaged SDK require explicit dirty-source
admission, and that activation plus status reject a non-CPython executable or
an interpreter shim whose eventual delegate is not bound. A synchronized
host-path replacement after wrapper verification proves that a deferred import
still reads the private verified snapshot. Wrapper execution under writable
directory modes is also proven not to create bytecode inside the immutable
release. A clean-checkout race between initial posture capture and release
hashing is proven to fail before wrapper or active-receipt publication. The
suite also rejects an unmanifested importable file from an otherwise
content-addressed release.

It also proves role-scoped MCP argv isolation: the selected AoA server alone is
configured, its exact token is required but never exposed in argv or the model
shell, and ambient/other MCPs are absent.

That suite does not prove the installed Codex binary, ChatGPT quota behavior,
Luna role performance, comparative net benefit, productive eval/stats/memo or
landing work, packaged four-owner compatibility, or live deployment. Those
require separate real-model and clean packaged-source receipts.
