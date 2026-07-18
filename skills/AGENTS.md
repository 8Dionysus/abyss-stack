# AGENTS.md

## Applies to

This card applies to `skills/` and its descendants.

## Role

`skills/` is the canonical home for agent procedures whose operational meaning
belongs to `abyss-stack`. It does not own the shared Agent Skills format,
cross-repository skill doctrine, or another repository's procedure.

## Read before editing

1. Root `AGENTS.md`, `CHARTER.md`, `BOUNDARIES.md`, and `DESIGN.md`
2. `skills/port.manifest.json`
3. The mechanic card and owner contract used by the affected bundle
4. The bundle `SKILL.md` and only the conditional references needed for the
   change

## Boundaries

- Keep the owner package authoritative for applicability, procedure, ABI,
  effects, verification, termination, and handoff.
- Keep semantic graphs, KAG records, installed copies, and runtime packets
  derivative of owner source.
- Expose admitted bundles once through the OS user profile. Do not duplicate an
  admitted owner bundle under `.agents/skills/`.
- Keep session traces, trial prompts, temporary rubrics, generated test
  fixtures, and task-local DAG state out of this directory.
- Treat techniques as optional provenance, never as a runtime dependency.
- Do not make a skill the enforcement owner for approval, mutation, service
  lifecycle, or security policy.

## Validation

Start with a manual positive, negative, owner-return, and coexistence pass.
After the behavior is understood, run the host skill package validator and the
narrow owner checks named by the bundle. For the diagnostic bundle, also run:

```bash
python scripts/build_diagnostic_surface_catalog.py --check
python scripts/validate_diagnostic_surface_catalog.py
python scripts/validate_stack.py
```

## Closeout

Report the owner package, manual cases, actual effects, skipped checks,
projection state, and remaining runtime or cross-model limits. A readable
package or green validator is not an effectiveness claim.
