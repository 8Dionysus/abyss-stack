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
assume-unchanged/skip-worktree mutations, and ignored bytes, a foreground
`run-to-terminal` lifecycle for transient cgroup launchers without execution
ceilings, secret-shaped ignored
input refusal, wrapped effect-family observation, exact validation-claim
binding to final workspace bytes, authority-blocked failure closeout when the
final manifest is unobservable, streaming rejection of an unterminated
oversized protocol record, review-gate enforcement, TERM-resistant and unexpected-worker-death
cleanup including a detached `setsid` descendant, high token/turn usage
measurement without truncation, durable interrupt/resume on one thread,
strict recovery of a complete main-session event append before state save,
partial-usage classification when interruption precedes Codex usage emission,
immutable preservation of the interrupted receipt across ordinary resume,
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
manifest binding, reviewer-result race refusal, wrapper-delimiter effect observation, final-manifest tamper refusal,
provenance checks for all loaded `aoa_sdk` modules in the study preparer plus a
post-compilation persisted
path inventory, produced-artifact admission, source-evidence file/line
validation including a source scope wider than mutation scope, reserved
runtime final-manifest evidence with false-anchor refusal, signal-notified
steady-state supervisor waiting, status-selected
wake binding, failed-reviewer A2A refusal, absence of an outer namespace that
would conflict with Codex sandboxing, and a separately bound review/A2A export.
It also proves parent obligation admission, a completed yield turn followed by
durable waiting, canonical child state/result/event receipt binding, rejection
of a standalone result, recovery of a valid event append that preceded its
state save, false-event filtering with no second parent turn, and exact-thread parent re-entry with a distilled
return. The fake Codex fixture exercises both filtered and wake branches;
separate live receipts are required for the installed product surface.

It also proves role-scoped MCP argv isolation: the selected AoA server alone is
configured, its exact token is required but never exposed in argv or the model
shell, and ambient/other MCPs are absent.

That suite does not prove the installed Codex binary, ChatGPT quota behavior,
Luna role performance, comparative net benefit, productive eval/stats/memo or
landing work, packaged four-owner compatibility, or live deployment. Those
require separate real-model and clean packaged-source receipts.
