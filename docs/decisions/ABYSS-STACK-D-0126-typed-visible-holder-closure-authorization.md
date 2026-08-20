# Typed Visible Holder Closure Authorization

- Decision ID: ABYSS-STACK-D-0126
- Status: accepted
- Date: 2026-08-20
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent`

## Index Metadata

- Original date: 2026-08-20
- Surface classes: public-contract, lifecycle
- Stack lanes: governed-execution
- Mechanic parents: `mechanics/governed-execution`
- Guard families: holder identity, terminal lifecycle, closure authorization
- Posture: accepted runtime rationale

## Context

The visible responsibility-holder closer was wake-receipt-centric. A direct
one-shot external holder can return through a non-waking join, but a generic
task-local return receipt did not prove the exact terminal action or authorize
the runtime closer. Treating output-file presence, semantic re-entry, or owner
acceptance as closure authority would collapse separate evidence planes and
could signal an unrelated or reused process.

## Options considered

- Wake-only closure: retain the existing route, leaving non-waking joins
  unable to close their exact terminal.
- A task-specific wrapper: recognize one launch script, version, title, or PID
  and close it by convention.
- Typed lifecycle authorization: keep wake delivery and non-waking join as
  distinct evidence kinds, bind both to the exact handoff/holder/terminal, and
  let one common closer consume the resulting authorization.

## Decision

Use typed runtime-owned closure authorization. `wake_delivered` is produced
from validated wake evidence; `join_completed` is produced by `join` only after
a returned handoff requires `close_exact_bound_holder`. Both authorizations
bind exact paths, digests, PIDs, and the required terminal action. `close`
accepts the authorization while retaining the legacy wake input for compatible
recovery. Closure receipts record the authorization kind and evidence.

## Rationale

This generalizes the owner boundary without importing role meaning or master
wake semantics into the runtime. It supports one-shot non-waking holders,
preserves fail-closed identity checks and recoverable reservations, and makes
the distinction between return, join, acceptance, re-entry, wake, and terminal
disappearance mechanically reviewable. The route is task-, version-, title-,
and PID-neutral.

## Consequences

- Positive: both wake-delivering and non-waking holders have one exact,
  reusable lifecycle close route with separate evidence and negative tests.
- Tradeoff: closure schemas and receipts move to v2 and old wake receipts need
  the compatibility `close --wake-receipt` route or a new authorization.
- Follow-up: a host canary must prove installed release use, exact holder and
  Kitty disappearance, and preservation of an unrelated live holder.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-holder-terminal-join.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-holder-terminal-closure-authorization.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-holder-terminal-closure.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`

## Follow-up route

The next live canary owner must provide the installed source/runtime release
identity and bounded process/terminal evidence. `aoa-agents` and the master
remain owners of responsibility transfer and wake; this decision does not
grant either semantic continuation or acceptance.
