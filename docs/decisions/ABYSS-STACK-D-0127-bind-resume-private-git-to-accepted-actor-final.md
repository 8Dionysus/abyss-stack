# Bind Resume Private-Git Observation to the Accepted Actor Final

- Decision ID: ABYSS-STACK-D-0127
- Status: proposed
- Date: 2026-08-20
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`

## Index Metadata

- Original date: 2026-08-20
- Surface classes: runtime continuity, actor projection, failure closeout
- Stack lanes: governed execution, runtime, validation
- Mechanic parents: governed-execution
- Guard families: projection continuity, private-Git drift, cumulative delta
- Posture: proposed owner-source rationale

## Context

An external actor resume starts from the exact final projection produced by its
preceding attempt. The runtime already uses that final manifest to reject a
projection that changed before the resumed model starts, but terminal and worker
failure closeout still used the original launch manifest as the private-Git
comparison witness. A reviewed prior projection could therefore be treated as
new private-Git drift at the next boundary, while the failure receipt lost the
actual continuity cause behind an observation-gap classification.

## Options considered

- Compare every resumed attempt with the original launch manifest. This keeps a
  single baseline but rejects an accepted prior projection.
- Replace the original baseline with the prior final manifest for all delta
  fields. This preserves continuity but loses the cumulative actor-owned
  content delta from the original workspace.
- Keep the original manifest as the cumulative content-delta origin and bind
  private-Git observation for a resumed attempt to the exact preceding actor
  final manifest.

## Decision

Use the third route. The runtime retains the original actor manifest for
`workspace_manifest_match` and content change enumeration. For `start`, the
original manifest is also the private-Git witness. For `resume`, the prior
durable `actor_final_manifest_ref` is the private-Git witness for the current
attempt. A private-Git digest change from that witness still raises the existing
fail-closed projection error in both normal and failure closeout.

## Rationale

The exact preceding final manifest is the only runtime-owned evidence that
binds the projection the actor was reviewed against. Separating its private-Git
witness from the original content-delta origin preserves both properties: an
accepted actor-owned delta remains resumable, and a new private-Git or out-of-
band change during the resumed attempt remains attributable and blocked. The
same relation is used on ordinary and failure closeout so manifest observation
failures retain their typed authority boundary.

## Consequences

- Positive: workspace-write actors can resume from an accepted prior projection
  without losing cumulative changed-path evidence.
- Positive: private-Git drift after that accepted projection remains fail-closed.
- Tradeoff: the resume path must retain and validate the preceding actor final
  manifest before a worker can continue.
- Unchanged: source checkout authority, owner acceptance, runtime admission,
  external effects, and preserved-writer live proof remain outside this source
  candidate.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_projection.py`
- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_projection.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

The root master should independently review this candidate, admit a runtime
containing it, and run the preserved writer's live resume proof. Revisit the
decision if the runtime adds a first-class per-attempt manifest schema instead
of deriving the witness from the prior final reference.
