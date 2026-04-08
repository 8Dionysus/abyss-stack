# DIAGNOSTIC SPINE

## Purpose

This note seeds the next honest self-diagnosis spine for `abyss-stack`.

The spine should unify runtime-body evidence into one runtime-owned diagnostic
read model while preserving clean handoff toward the newer session-level
diagnosis, repair, progression, and quest-harvest family.

The goal is not a louder doctor.
The goal is a clearer answer to four questions:

1. what path is being diagnosed
2. what evidence is actually present
3. what drift or gap is real
4. what is the next honest move

## Core stance

The diagnostic spine is a read model with memory.

It may:
- resolve selectors into a concrete diagnostic target
- gather runtime-body signals
- normalize them into a stable artifact
- compare against last-good posture when available
- emit explicit next-move classes
- hand off to reviewed session diagnosis or repair surfaces by citation

It must not:
- replace `aoa-doctor`
- replace `aoa-status --autonomy`
- replace reviewed `DIAGNOSIS_PACKET` or `REPAIR_PACKET` owner surfaces
- grant silent mutation authority
- widen RPG, quest, or progression ownership
- smuggle source-owned meaning into runtime-local canon

## Why now

The stack now has:
- runtime-body readiness and posture surfaces
- questbook / quest artifacts for explicit follow-through
- RPG runtime collections as read-model transport
- session-level self-diagnose, self-repair, progression, and quest-harvest skills

That makes it possible to build a more coherent self-diagnosis loop without
collapsing those layers into one blob.

## Proposed runtime-owned objects

### 1. `diagnostic_target_v1`

A resolved contract for the path being diagnosed.

Suggested concerns:
- selected preset and profiles
- truth goal for this pass
- required checks
- expected service classes
- expected internal probes
- drift watch classes
- fallback candidates
- public-safe posture

The key idea is that self-diagnosis should locate itself before it judges
itself.

### 2. `diagnostic_session_v1`

A runtime-owned artifact that captures one normalized diagnosis pass.

Suggested concerns:
- target contract
- multi-axis verdicts
- truth-status posture
- named drift classes
- explicit unknowns
- strong evidence refs
- exit class
- ranked next moves
- public-safe posture

This artifact should be compact, machine-readable, and citation-friendly.

### 3. `diagnosis_companion_v1`

A runtime-owned diagnosis bridge that stays packet-shaped enough to review,
without pretending it replaces the owner-layer `DIAGNOSIS_PACKET`.

This object should:
- cite one concrete `diagnostic_session_v1`
- separate symptom from probable cause
- name likely owner hints and bounded repair shapes
- stay review-oriented when the next honest move is still diagnosis before repair

### 4. `diagnostic_anchor_ref_v1`

A remembered `last-good` comparison anchor for a given diagnostic target.

This is not a proof surface.
It is a bounded runtime memory of the latest known-good posture for a specific
target shape.

### 5. `reviewed_diagnosis_ref_v1`

An explicit review bridge over `diagnosis_companion_v1`.

This is still not a `DIAGNOSIS_PACKET`.
It is a bounded citation artifact that says whether the current runtime-local
diagnosis is good enough to support repair handoff, should be retested first,
or is not yet repair-fit.

This object should:
- cite the current `diagnostic_session_v1`
- cite the runtime-owned `diagnosis_companion_v1`
- record a reviewer label and review verdict
- keep diagnosis-first uncertainty explicit instead of silently promoting repair

### 6. `repair_handoff_v1`

A runtime-owned handoff artifact that keeps repair posture explicit without
pretending a `REPAIR_PACKET` already exists.

This object should:
- cite the current `diagnostic_session_v1`
- cite any reviewed companion session refs
- state whether repair is `not_needed`, `review_required`, `ready_for_review`, or `blocked`
- name checkpoint posture and escalation routes toward the real owner layer

## Suggested axes

Use multiple axes instead of one global green/red light.

Suggested first-wave axes:
- `readiness`
- `posture`
- `render_truth`
- `runtime_health`
- `closure`
- `evidence`
- `governability`

Each axis may independently be:
- `pass`
- `warn`
- `fail`
- `skipped`
- `unknown`

## Suggested truth-status vocabulary

Reuse the stack's existing staged-truth posture instead of flattening
everything into one boolean.

Suggested flags:
- `source_authored`
- `deployed`
- `trial_proven`
- `live_available`

This avoids declaring a pre-deploy or trial-only state "broken" just because it
is not yet fully live.

## Drift taxonomy

A first useful taxonomy is:

- `selector_drift`
- `source_deploy_drift`
- `host_posture_drift`
- `adaptation_staleness`
- `render_truth_drift`
- `runtime_health_drift`
- `closure_drift`
- `truth_gap`
- `noise_envelope`
- `policy_gate_block`
- `evidence_gap`
- `boundary_confusion`

The taxonomy should stay descriptive.
It should not pretend to prove more than the evidence supports.

## Exit classes

Suggested first-wave exit classes:

- `ready_to_start`
- `running_as_intended`
- `running_but_unproven`
- `trial_proven_not_live`
- `live_but_drifted`
- `repairable_under_governance`
- `manual_reground_required`

These classes are meant to reduce panic-churn.
A system can be imperfect without being "mysteriously broken".

## Storage posture

Suggested live path:

```text
${AOA_STACK_ROOT}/Logs/diagnostics/latest/
  diagnostic_target.json
  diagnostic_session.json
  diagnosis_companion.json
  repair_handoff.json
  reviewed_diagnosis.ref.json
  last_good.ref.json
```

Suggested history path:

```text
${AOA_STACK_ROOT}/Logs/diagnostics/records/
```

Public-safe source-managed examples may live under:

```text
examples/
```

The runtime may prefer the live `Logs/diagnostics/latest/` copies.
Examples remain examples and are not runtime authority.

## Current read-only CLI seam

The first read-only seam now looks like:

```bash
scripts/aoa-diagnose --preset intel-full --truth-goal live_available
scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest
scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest --write-last-good-ref
scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest --write-reviewed-diagnosis-ref
scripts/aoa-diagnose --preset agent-full --against last-good --write /tmp/diagnostic_session.json
scripts/aoa-diagnose --preset intel-full --with-session-ref /path/to/reviewed-session.json --write-latest
scripts/aoa-diagnose --preset intel-full --with-reviewed-diagnosis-ref /path/to/reviewed-diagnosis.packet.json --write-latest
```

The seam stays read-only:
- it resolves selectors through the same profile logic as the runtime wrappers
- it gathers bounded evidence from `aoa-doctor`, `aoa-status --autonomy --json`, rendered service shape, and existing `Logs/*` refs
- it may write `diagnostic_target.json`, `diagnostic_session.json`, `diagnosis_companion.json`, `repair_handoff.json`, and `reviewed_diagnosis.ref.json` under `Logs/diagnostics/{latest,records}/`
- it may refresh `last_good.ref.json` only through the explicit `--write-last-good-ref` flag when the current pass is green for its truth goal
- it may write `reviewed_diagnosis.ref.json` only through the explicit `--write-reviewed-diagnosis-ref` flag when the current pass is drifted enough to justify diagnosis review
- it still does not mutate repair state

## Handoff posture

The runtime diagnostic spine may cite or hand off toward:

- `aoa-session-self-diagnose`
- `aoa-session-self-repair`
- `aoa-session-progression-lift`
- `aoa-quest-harvest`

Skill canon remains in `aoa-skills`.
Any local overlay should stay thin, repo-relative, and sourced from that
canonical skill surface.
The repo-local install surface for this pass is
`.agents/skills/abyss-self-diagnostic-spine`.

But the runtime spine must not absorb those owner surfaces.

Good examples of honest handoff:
- "emit `repair_packet_candidate` because the route is bounded and already diagnosed"
- "emit `quest_followup` because the gap repeats but should stay explicit"
- "emit `manual_reground_required` because the issue crosses owner boundaries"
- "emit `progression_lift_candidate` because the reviewed evidence reflects stable capability change"

## Minimal landing recommendation

A small honest first pass would be:

1. land this note
2. land `diagnostic_target_v1` and `diagnostic_session_v1` schemas
3. add one quest draft
4. install one thin local Codex-facing overlay skill at `.agents/skills/abyss-self-diagnostic-spine`, sourced from `aoa-skills`
5. postpone real mutation or orchestration code until the read model proves useful

## Guardrails

- diagnostics remain descriptive and citation-oriented
- self-diagnosis is not free self-repair
- review or approval posture is not bypassed
- RPG remains reflective
- quest state is not auto-mutated by runtime diagnosis
- progression stays multi-axis and evidence-backed
- public-safe defaults stay strong

## Final rule

A strong diagnostic spine gives the system self-location before self-assertion.
