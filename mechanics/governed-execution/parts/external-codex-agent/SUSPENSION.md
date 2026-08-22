# Suspension and rollback

Suspension is an owner-controlled runtime transition, not a model decision and
not deletion of evidence. The current source supports exact `owner_contour`
admission as well as bounded `transport_study_fixture` compatibility evidence;
it is not yet a clean installed release, a model-fit verdict, or authority for
an external effect.

## Suspend new work

The caller or future registration owner must stop issuing new launch
admissions first. This part deliberately has no global enable switch and must
not mutate a shared router, service, or model catalog to simulate one.

For already known sessions, use the exact state root and session ID from the
launch/result receipt:

```bash
PYTHONPATH=/absolute/path/to/aoa-sdk/src \
python scripts/aoa-external-codex-agent \
  --state-root /absolute/path/to/state-root \
  --session-id 'session:exact-id' \
  status
```

If and only if that exact session is still `running`, request the controller's
bounded interruption:

```bash
PYTHONPATH=/absolute/path/to/aoa-sdk/src \
python scripts/aoa-external-codex-agent \
  --state-root /absolute/path/to/state-root \
  --session-id 'session:exact-id' \
  interrupt
```

Do not replace this with generic process killing. The controller verifies the
recorded worker, supervisor, and Codex identities, contains descendants, emits
an interruption result, and preserves the event cursor and partial-usage gap.
If an exact identity cannot be validated, stop and route the state to the
runtime owner; do not broaden the target or retry with a stronger primitive.

## Pause an exact Goal after responsibility transfer

When responsibility has moved to an external holder and the master must pause
its own Goal, use the owner-selected app-server lifecycle leaf:

```bash
aoa-external-codex-return pause \
  --pause-owner /absolute/path/to/pause-owner.json \
  --pause-receipt /absolute/path/to/pause-receipt.json
```

The pause owner must bind the exact Goal and thread. The leaf reads the current
Goal first, refuses anything other than `active`, calls the supported
`thread/goal/set` API with `paused`, and records
`abyss_stack_external_codex_pause_receipt_v1`. It does not inject terminal
input, inspect or signal PIDs, use GDB, start or steer a turn, deliver a wake,
or close any holder. A receipt proves only the runtime lifecycle transition;
 wake delivery, holder closure, semantic re-entry, and owner acceptance require
 their own later evidence. If the pause receipt is absent or the Goal state is
 not exactly bound, stop and route the state to the runtime owner. A reserved
 pause keeps the active precondition before mutation and records a dispatch
 marker only after this attempt has issued the exact WebSocket
  `thread/goal/set` request. If a retry observes the exact Goal already paused,
  it may publish an `ambiguous_post_mutation` recovery receipt from a read-only
  `thread/goal/get` without issuing a second lifecycle set only when that marker
  matches the attempt and request and the resolved app-server endpoint matches
  the endpoint recorded before mutation. If the Goal is still `active` after a
  dispatch marker exists, the retry fails closed rather than replacing that
  attempt. A reserved pause without the precondition or dispatch evidence fails
  closed, including when another controller may have paused the Goal after this
  attempt stopped before issuing its request. A persisted receipt with
  `response_available=false` must retain its recovery evidence and its
  `pause_receipt_ref` must match the exact output path; a copied or incomplete
  receipt is not replayable.

For a parent continuation, inspect only its exact state root and re-entry ID:

```bash
PYTHONPATH=/absolute/path/to/aoa-sdk/src \
python scripts/aoa-external-codex-agent \
  reentry-status \
  --state-root /absolute/path/to/reentry-state-root \
  --reentry-id 'reentry:exact-id'
```

A `yielding` or `yielded` parent must be inspected before retry: preserve every
numbered turn attempt, and do not overlap a still-live recorded supervisor. A
`waiting` parent has no Sol inference to kill. Suspending it means preserving
the obligation, event stream, yielded thread ID, and child evidence while not
calling `reenter-parent`. Do not synthesize a wake, edit the state, or resume
the thread directly. A `filtered`, `reentered`, or `failed` cycle is terminal
evidence; prepare a new owner-reviewed obligation rather than retrying it.

## Preserve before any rollback

Keep the complete session directory, including admitted inputs, every attempt,
process identities, raw and normalized events, stderr, prior terminal results,
model reports, final workspace manifests, wake evaluations, and A2A returns.
Do not delete or rewrite failed, interrupted, review-required, or superseded
study evidence.

For a bounded workspace-write task, preserve the target owner's exact baseline,
post-write manifest, changed-path receipt, validator output, and review result.
Restoring source is an owner-specific change and must follow that repository's
rollback/re-entry route; this runtime never uses a generic checkout reset as an
acceptance mechanism.

## Resume or roll back

Resume is allowed only when the exact durable thread, current event cursor,
continuation obligation, task authority, immutable inputs, runtime profile,
and digest-bound follow-up still match. A suspension does not imply permission
to resume. Provider/catalog drift, target drift, unresolved review findings, or
withdrawn owner authority requires a new owner decision or a fresh preparation.
An exact pre-turn ChatGPT usage-limit failure may resume through
`capacity_recovery` only after capacity is available and only when its prior
result, raw terminal event pair, empty effect history, manifests, session,
thread, cursor, and result digest all still verify. Do not probe recovery by
repeatedly consuming new attempts while the provider limit remains active.

If this source candidate later lands and must be rolled back, the source owner
reverts the exact landed change through its normal reviewed route and the
consumer/registration owner restores its prior runtime adapter or leaves the
lane unregistered. Runtime state remains evidence and is not rolled back with
the code. Before clean activation, rollback is non-activation plus preservation
of the isolated worktrees and receipts. After activation, restore the prior
immutable release through `install_external_codex_runtime.py activate`; do not
delete the later release or runtime evidence.

## Suspension triggers

Suspend or keep the lane non-admitted when any of these is observed:

- executable, model catalog, realization, runtime profile, SDK plan, summon,
  task, schema, workspace, or immutable-input identity drift;
- secret-shaped input, forbidden effect, out-of-scope mutation, or unobservable
  command activity;
- repeated process containment or process-death recovery failure;
- invalid or drifted review/A2A evidence;
- false readiness, owner ambiguity, unclear rollback, or reviewer disagreement
  requiring stronger judgment;
- proof-owner rejection, target-owner withdrawal, provider access loss, or
  evidence that total review/rework cost erases the expected benefit.

Transport suspension does not weaken or retract a model claim by itself.
`aoa-models` owns that lifecycle update, `aoa-evals` owns proof meaning, and the
human operator remains the only human acceptance authority.
