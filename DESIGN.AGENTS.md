# DESIGN.AGENTS.md

Agent-surface design for `abyss-stack`.

## Role

This file describes the intended form of `AGENTS.md` guidance in `abyss-stack`.
It is not the root `AGENTS.md`, not a prompt library, not a policy engine, and
not a replacement for local route cards.

It answers one question: how should agent-facing instructions be shaped so
future work can move through runtime infrastructure without losing boundaries,
validation, or return paths?

## Thesis

Agent guidance in `abyss-stack` should be a navigable route mesh. The root card
sets identity and broad safety. Local cards narrow scope. Package and part cards
name ownership, risk, and checks. Validators keep the mesh honest.

The aim is not more instruction volume. The aim is less guessing.

## Anatomy

The agent route mesh has these layers:

- **root card**: `AGENTS.md`, the repository-wide route card
- **design cards**: `DESIGN.md` for runtime form and this file for agent-surface
  form
- **district cards**: local cards for `compose/`, `config-templates/`, `env/`,
  `systemd/`, `scripts/`, `MCP/`, `memo/`, `docs/`, `tests/`, `.agents/`,
  `.github/`, and other root districts
- **mechanic package cards**: `mechanics/<package>/AGENTS.md` cards for runtime
  move families
- **part cards**: `mechanics/<package>/parts/<part>/AGENTS.md` cards when a part
  has its own risk, commands, schemas, examples, or validation
- **legacy and provenance cards**: bounded route surfaces that explain preserved
  history without letting legacy names become active topology
- **validation surfaces**: `validate_stack.py`, nested-agent checks, tests,
  catalog builders, and CI that enforce the route mesh
- **generated companions**: indexes and catalogs that help navigation while
  staying subordinate to source cards

## Canonical Card Shape

Use this shape for new or heavily revised route cards unless a local surface has
a clear reason to be smaller:

```markdown
# AGENTS.md

## Applies to

## Role

## Read before editing

## Boundaries

## Validation

## Closeout
```

Optional sections may include `Purpose`, `Owner Lane`, `Route Modes`, `Source
Surfaces`, `Runtime Rules`, `Post-change Route Review`, `Hard No`, or
`Review-critical Drift` when they clarify a real local contract.

Do not add decorative sections that do not change how an agent should act.

## Operation

When an agent enters a surface:

1. Read the root `AGENTS.md`.
2. Read the nearest local `AGENTS.md` for every touched path.
3. Read the local README, package card, or part card named by that route.
4. Identify whether the change is source, runtime, generated, legacy,
   diagnostic, public-share, or private-state work.
5. Choose the narrowest validator that proves the changed contract.
6. Close with changed surfaces, verification, skipped checks, and remaining
   route risk.

For large topology moves, update this mesh before continuing the move. A
refactor that leaves future agents unsure where to stand is not complete.

## Authority Boundaries

Agent guidance may tell agents where to look and what to verify. It must not:

- claim live runtime state from source-only evidence
- make sibling repository doctrine local to `abyss-stack`
- make generated artifacts authoritative over source surfaces
- hide infra, host exposure, secret, storage, or lifecycle risk under docs-only
  wording
- keep legacy names as active topology when a current package, part, bridge, or
  provenance route exists

## Design Principles

- **Locality before abstraction.** A local card should answer the local risk
  before pointing outward.
- **Routes before commands.** Commands are useful only after the owning surface
  is clear.
- **Source before instruction.** `AGENTS.md` should point to source surfaces
  rather than re-authoring all of their content.
- **Negative boundaries matter.** A good card says what does not belong.
- **Validation handshake.** Every meaningful card should name the check that
  proves its surface.
- **Closeout memory.** Reports should leave enough evidence for the next agent
  to resume without reconstructing the whole session.
- **Generated companions stay weaker.** Generated maps may summarize the route
  mesh, but source cards own the contracts.
- **Proximity narrows.** The deeper the path, the more concrete the guidance
  should become.
- **Portability through repeated shape.** A recurring card shape makes future
  passes faster without flattening local differences.

## Good Agent Surfaces Feel Like

- a new agent can find the owner, risk, and validator within one or two hops
- a root card stays short enough to be read before work starts
- local cards prevent accidental edits to runtime mirrors, generated surfaces,
  legacy homes, or sibling-owned truth
- validators name missing cards and stale route drift before those mistakes
  become project memory

## Bad Agent Surfaces Smell Like

- root guidance tries to be the whole repository manual
- local cards repeat doctrine without naming local files, risks, or checks
- a package has parts but no route for part-owned docs, schemas, examples, or
  tests
- legacy folders are silent dumping grounds instead of provenance-preserving
  bridges
- closeout says "validated" without naming the actual check

## Use by Agents

When editing `AGENTS.md` files, `.agents/` overlays, local route cards, or
validator checks that enforce route-card coverage, use this file as the design
reference. If local reality needs a different shape, keep the deviation small
and record the reason in the owning surface or a decision note.
