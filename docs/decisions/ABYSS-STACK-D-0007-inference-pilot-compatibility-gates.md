# Inference Pilot Compatibility Gates

- Decision ID: ABYSS-STACK-D-0007
- Status: accepted
- Date: 2026-05-13
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-13
- Surface classes: mechanic part, validation guard
- Stack lanes: inference pilots
- Mechanic parents: inference-pilots
- Guard families: validation lane, service selection
- Posture: accepted compatibility gate rationale

## Context

`aoa-local-ai-trials` preserves an older W0-W4 runner API because runtime
artifacts, schemas, and operator packets still rely on those wire IDs. After
the first-run and local-trials refactors, the active LangGraph and llama.cpp
pilot surfaces still described `W0` and `W4` as if they were current topology
names.

That made the source tree look flatter than it is: old runner lineage was
already contained, but active docs and wrappers still carried wave-shaped
language.

## Options considered

1. Rename every preserved W0/W4/W5/W6 value immediately.
2. Keep the preserved values visible as active topology names.
3. Preserve old values only as compatibility IDs behind quiet active bridge names.

## Decision

Keep `W0` and `W4` as compatibility IDs only.

Active inference-pilot surfaces now name their responsibilities as:

- runtime compatibility gate for the preserved `W0` wire ID
- edit fixture compatibility gate for the preserved `W4` wire ID
- bounded-edit compatibility gate for the LangGraph sidecar contract
- long-horizon and bounded-autonomy pilot indexes for preserved `W5`/`W6`
  runtime artifact names

The active code may still pass `W0`, `W4`, and `wave_id` into the preserved
runner schemas and artifact paths, and may still read `W5`/`W6` runtime index
files. It must route those tokens through compatibility or preserved-artifact
constants, not through active topology names such as waves.

The active role-level bridge is
`mechanics/inference-pilots/parts/local-trials/trial_compatibility_bridge.py`.
Older legacy wording belongs in `legacy/trials/`; active imports should use the
quiet bridge name.

The LangGraph dependency manifest belongs with the LangGraph part at
`mechanics/inference-pilots/parts/langgraph-pilot/requirements.txt`, not under
the root command wrapper directory.

## Rationale

Compatibility IDs are real runtime contracts, but they should not teach old family labels as the current topology. A quiet bridge keeps existing artifacts usable while letting active docs, wrappers, and validators speak in role-level names.

## Consequences

- Runtime artifact compatibility remains intact.
- Active docs and wrapper help no longer teach the old runner labels as the
  current topology.
- `scripts/validate_stack.py` now checks that LangGraph, llama.cpp, and
  autonomy-status surfaces keep the compatibility-gate language and do not
  reintroduce old wave-shaped prose outside the preserved legacy runner.
- The root `scripts/` directory remains a command-wrapper surface, not a
  dependency-manifest home for part-owned pilots.

## Source surfaces

- `mechanics/inference-pilots/parts/local-trials/trial_compatibility_bridge.py`
- `mechanics/inference-pilots/parts/langgraph-pilot/`
- `mechanics/inference-pilots/parts/llamacpp-pilot/`
- `scripts/validate_stack.py`

## Follow-up route

Remove compatibility IDs only after the stronger owner and existing runtime artifacts have clean replacements; until then, keep them behind bridge constants and compatibility docs.
