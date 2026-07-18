# Diagnostic Skill Owner Home

- Decision ID: ABYSS-STACK-D-0080
- Status: accepted
- Date: 2026-07-17
- Owner surface: `skills/abyss-self-diagnostic-spine/`

## Index Metadata

- Original date: 2026-07-17
- Surface classes: owner skill home, agent skill projection, source/derived boundary
- Stack lanes: source checkout, agent surface, diagnostics
- Mechanic parents: diagnostic-spine
- Guard families: owner source return, read-only diagnosis, effect boundary, skill projection
- Posture: accepted owner-skill admission

## Context

The diagnostic skill began as shared `aoa-skills` canon with a thin
`abyss-stack/.agents/skills` overlay. That split made the repository owning the
CLI, schemas, typed packet, drift vocabulary, and truth axes weaker than a
generic skill repository, while Codex could also discover duplicate copies from
repository and user roots.

The later semantic capability graph preserved a diagnostic node but did not
preserve the complete procedure or create a reliable source-return path. The
runtime capability therefore needs one canonical owner package and one
OS-selected user projection.

## Options considered

1. Keep the procedure in `aoa-skills` and retain the repo-local overlay.
2. Treat `.agents/skills/abyss-self-diagnostic-spine` as the canonical package.
3. Place the canonical package under `abyss-stack/skills/`, expose it once
   through the OS user profile, and leave graphs and installed copies derived.

## Decision

Choose option 3.

Admit `skills/abyss-self-diagnostic-spine/` as the canonical owner package for
the stack diagnostic procedure. Remove its `.agents/skills` duplicate. Declare
user-scoped exposure through `skills/port.manifest.json`; the OS profile owns
installation and writes a same-bundle `.aoa-skill-source.json` locator into
the installed copy.

The package selects exactly one of `observe`, `capture`, or `review`, preserves
typed non-zero diagnostic outcomes, distinguishes truth axes, and stops before
repair or unrequested promotion. `aoa-skills` may model and compose the
capability but no longer authors this owner-specific procedure.

The remaining shared `.agents/skills` links are a separate transitional
projection and are not removed by this decision before their global OS
replacements are available.

## Rationale

Manual trials covered invalid external packets, read-only owner observation,
explicit bounded capture, a natural diagnostic request, a generic-health
negative, stale current-evidence rejection, duplicate user/repository
discovery, and coexistence with shared session recovery. The owner candidate
returned to exact stack sources, preserved effect boundaries, stopped a stale
packet as `blocked_current_observation_required`, and loaded recovery only
after a schema-valid packet produced a bounded repair-fit handoff. It did not
turn diagnosis into repair.

The trials also exposed unnecessary duplicate owner reads, premature doctrine
loading, broad packet dumps, and a heredoc validation attempt. The admitted
procedure now switches to owner references after receipt resolution, keeps
routine owner docs conditional, and requires bounded inline validation output
before packet claims. Those corrections were repeated on the same manual
paths; no trial trace or temporary validator became source.

The useful behavior comes from owner-specific selection, typed output handling,
freshness review, and termination. A graph node, copied overlay, or green
frontmatter check does not provide those functions. Owner source plus one user
projection preserves both functionality and discoverability without competing
copies.

## Consequences

- Positive: the repository that owns diagnostic meaning now owns its agent
  procedure and contract.
- Positive: the global catalog can advertise one copy with an exact
  owner/ref/path/version/digest return handle.
- Positive: raw trial prompts, task-local state, and temporary rubrics remain
  outside source.
- Tradeoff: owner-source parity and fresh-session discovery still depend on
  the federated OS profile and must be rechecked after material host or model
  changes.
- Tradeoff: the general `.agents/skills` projection validator remains until
  the separate shared-projection migration lands; only its diagnostic-overlay
  exception is removed here.
- Limit: admission does not prove cross-model equivalence, runtime health, or
  repair success.

## Source surfaces

- `skills/AGENTS.md`
- `skills/port.manifest.json`
- `skills/abyss-self-diagnostic-spine/SKILL.md`
- `skills/abyss-self-diagnostic-spine/references/contract.yaml`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`
- `scripts/aoa-diagnose`
- `scripts/validators/diagnostic_spine.py`
- `docs/decisions/ABYSS-STACK-D-0062-agent-skill-projection-validator-module.md`

## Follow-up route

The OS skill profile must install and verify the owner package without a
same-name repository projection. Re-run natural discovery, negative,
source-return, and recovery coexistence trials after material skill, CLI,
schema, host, model, or catalog changes.
