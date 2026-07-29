# Agent OS Adapter

This part owns the `abyss-stack` production bridge for the `aoa-sdk` Agent OS
control plane.

The bridge is a local subprocess JSON interface. It persists runtime-owned
session state and admits three exact owner-pinned lanes. `AOA-P-0011`
repository mutation delegates to the existing governed runner. `AOA-P-0031`
reviews a typed A2A return without executing a child, and `AOA-P-0032` carries
an owner degradation receipt through durable pause, restore, and resume. It is
not a daemon, listener, route resolver, generic plan interpreter, playbook
author, eval organ, memory organ, or closeout authority.

Compilation-ready profiles retain the selected lane's exact runtime approval
projection. The bridge compares descriptor, profile, and plan instead of
accepting approvals inserted after compilation.

Every mutating dispatch refreshes and validates the pinned source/ABI
observation before backend execution. That observation reads each bounded
artifact once, hashes those exact bytes, and retains a private read-only
materialization under the runtime state root. Runtime semantics, typed-lane
inputs, governed request/policy preparation, and emitted input evidence all
consume the captured bytes rather than reopening the caller-controlled
coordinates after admission. Approval decisions are admitted only for the
single current request and only before that request has a durable decision,
so an old rejection cannot rewrite an advanced or completed run. An approved
plan-freeze decision repeats the same snapshot gate before the preview backend
can run. The decision and a pending effect journal are persisted before the
governed approval file or preview backend changes. Exact decision replay
continues only the unfinished journal phase; it does not append another
decision or event. The governed start command and its deterministic run
identity are journaled before preparation, so an exact replay can recover the
existing result without creating another run or repeating provider work.

The admitted contours carry no retry attempts. A transient governed preview
interruption therefore stays paused behind exact decision replay, while a
transient final continuation stays paused behind a new explicit resume
command. Neither condition is mislabeled as a recoverable failure that the
plan could never recover.

Constraint admission compares the descriptor-declared owner, artifact,
source, schema, and schema version. The plan snapshot separately binds the
runtime policy bytes, so a caller cannot substitute a weakened policy while
retaining only the expected owner/artifact key.

Evidence admission compares the complete requirement set, including producer
and binding class, and A2A return review accepts only non-empty string artifact
identifiers. Unadmitted evidence cannot be hidden by a filter or reach a
generic runtime error. Emitted evidence claims are derived from present
lane artifacts; governed failure never inherits unproduced terminal coverage.

The Python bridge must be paired with an explicit installed-SDK interpreter
and isolated mode; the executable shebang is an operator convenience, not the
package-binding contract.

For C5, cross-owner evidence completeness is validated by the SDK before
dispatch. This runtime owner accepts only the exact final closeout ref and
validates its plan, session, outcome, and owner scope.

The active contract is [CONTRACT](CONTRACT.md), the exact supported profile
and plan-to-runtime mapping is [runtime-profile.v1.json](runtime-profile.v1.json),
and the focused checks are listed in [VALIDATION](VALIDATION.md).
