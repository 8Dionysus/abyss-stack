# Retry Only Transient Actor-Manifest Observation Races

- Decision ID: ABYSS-STACK-D-0114
- Status: accepted
- Date: 2026-08-11
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-11
- Surface classes: runtime boundary, actor projection, validation evidence
- Stack lanes: runtime, evidence, validation
- Mechanic parents: governed-execution
- Guard families: full manifest, fail closed, bounded retry
- Posture: accepted bounded observation recovery; no authority widening

## Context

Owner-contour landing writers exposed two short-lived inventory races while
binding fixed validation claims to workspace bytes. One attempt observed a
regular file changing during its read. A later attempt queued a directory that
disappeared before `scandir`. Both terminated otherwise healthy actors as
`actor_projection_observation_gap`.

The inventory correctly refuses partial or inconsistent bytes. Treating every
regular-file read race as permanent, however, makes real workspace-write roles
dependent on an accidental quiescent instant. The failure record also retained
the stable code but discarded the originating observation message, weakening
diagnosis.

## Options considered

- Keep one-shot inventory and require actors to add arbitrary sleeps before
  every validation command.
- Retry every projection error until a manifest can be built.
- Retry only regular-file identity/read races and a disappearing-directory
  enumeration race for a small fixed number of attempts, rebuilding the entire
  manifest each time.

## Decision

Actor-manifest observation receives three total attempts separated by a short
fixed delay only when `external_codex_projection` proves that a regular file
changed while being read, its post-read identity changed, or a directory
disappeared before its queued enumeration. Every attempt rebuilds the complete
descriptor-bound manifest; no bytes from a failed attempt are admitted.

All other projection errors remain immediately terminal, including unsafe or
outward symlinks, special entries, missing coordinates, enumeration failures
other than the exact absent-directory race, private Git-body drift, path
replacement, and source identity drift. A qualifying race that persists
through the bounded attempts also remains
`actor_projection_observation_gap`.

When event observation terminates an actor, the runtime carries the original
error text into the durable failure report alongside its stable failure code.

## Rationale

The retry handles temporal instability in observation, not uncertainty about
authority or admissible content. Rebuilding the entire manifest after the tree
stabilizes preserves the same proof target. Restricting retry eligibility to
explicit race messages and distinguishing `FileNotFoundError` from other
`scandir` failures prevents a transient special entry, permission failure, or
coordinate violation from being laundered by disappearance before a later
snapshot. The manifest proves state at the command-completion observation
point; it is not a history of every temporary inode created and removed by an
admitted command.

## Consequences

- Positive: real workspace-write actors can validate final artifacts without
  failing on narrow file-read or directory-enumeration races.
- Positive: exact validation-command receipts still bind to one complete
  content-addressed manifest.
- Positive: durable failures retain actionable observation detail.
- Tradeoff: a qualifying race may delay event processing by a small fixed
  interval.
- Follow-up: rerun the Luna landing writer-to-reviewer vertical slice and keep
  every prior failed incarnation as counterevidence.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

`abyss-stack` owns the physical manifest observation and failure evidence.
`aoa-agents` continues to own role mandate and responsibility; `aoa-models`
continues to own realization fit; and `aoa-sdk` continues to own binding and
continuation meaning. A broader retry policy requires a new owner decision.
