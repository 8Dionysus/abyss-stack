# Validation

Run the paired source proof with the exact `aoa-sdk` checkout that owns
`AgentIncarnationBinding`:

```bash
AOA_SDK_SOURCE_ROOT=/absolute/path/to/aoa-sdk \
PYTHONPATH=/absolute/path/to/aoa-sdk/src \
python -m pytest -q \
  mechanics/governed-execution/parts/external-codex-agent/tests

PYTHONPATH=/absolute/path/to/aoa-sdk/src \
python -m py_compile \
  scripts/aoa-external-codex-agent \
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
binary. It proves exact fixture-only admission, a distinct OS process,
structured events and output, no built-in multi-agent flag, byte-aware
read-only drift containment including ignored bytes, a foreground
`run-to-terminal` lifecycle for transient cgroup launchers without execution
ceilings, secret-shaped ignored
input refusal, wrapped effect-family observation, exact validation-claim
binding, review-gate enforcement, TERM-resistant and unexpected-worker-death
cleanup including a detached `setsid` descendant, high token/turn usage
measurement without truncation, durable interrupt/resume on one thread,
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
manifest binding, wrapper-delimiter effect observation, final-manifest tamper refusal,
provenance checks for all loaded `aoa_sdk` modules in the study preparer plus a
post-compilation persisted
path inventory, produced-artifact admission, source-evidence file/line
validation including a source scope wider than mutation scope, reserved
runtime final-manifest evidence with false-anchor refusal, signal-notified
steady-state supervisor waiting, status-selected
wake binding, failed-reviewer A2A refusal, absence of an outer namespace that
would conflict with Codex sandboxing, and a separately bound review/A2A export.
It also proves parent obligation admission, a completed yield turn followed by
durable waiting, exact child-result/event binding, false-event filtering with
no second parent turn, and exact-thread parent re-entry with a distilled
return. The fake Codex fixture exercises both filtered and wake branches;
separate live receipts are required for the installed product surface.

That suite does not prove the installed Codex binary, ChatGPT quota behavior,
Luna quality, comparative net benefit, productive landing work, packaged SDK
compatibility, or live deployment. Those require separate real-model and
packaged-source receipts.
