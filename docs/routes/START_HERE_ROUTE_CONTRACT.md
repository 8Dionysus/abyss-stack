# Start Here Route Contract

This is the route-mode contract for the `abyss-stack` source checkout.

The canonical file path is `docs/routes/START_HERE_ROUTE_CONTRACT.md`.

Use this file when a reader, agent, validator, or future route surface needs to
choose the first correct owner surface without turning root README, docs root,
or roadmap into an inventory.

## Contract Rule

Entry surfaces may summarize route modes, but this file owns their current
meaning for `abyss-stack`.

The route modes are reflected in:

- `README.md`
- `AGENTS.md`
- `docs/README.md`
- `docs/AGENTS.md`
- `scripts/validate_stack.py`
- `tests/test_current_direction_routes.py`

If one of those surfaces changes the route order or adds a route mode, the
others must move in the same change.

## Route Modes

| Route mode | Audience | Job | Canonical path |
|---|---|---|---|
| `first-reading` | humans, new agents, outside readers | understand the runtime source checkout without entering every package | `README.md` -> `CHARTER.md` -> `BOUNDARIES.md` -> `DESIGN.md` -> `mechanics/README.md` |
| `runtime-design` | maintainers, topology editors, reviewers | change runtime form, source/runtime split, topology, or generated/source authority | first reading -> `DESIGN.md` -> `docs/runtime/ARCHITECTURE.md` |
| `agent-guidance` | coding agents, route-card editors, reviewers | change root or nested agent guidance without losing local ownership | `AGENTS.md` -> `DESIGN.AGENTS.md` -> nearest nested `AGENTS.md` |
| `source-install` | operators, release agents, setup editors | create or refresh a runtime layout from a source checkout | `docs/runtime/PATHS.md` -> `docs/install/DEPLOYMENT.md` -> `mechanics/config-projection/README.md` -> `mechanics/runtime-lifecycle/README.md` |
| `runtime-operation` | operators, incident reviewers, lifecycle editors | operate, inspect, smoke, log, or intentionally check deployed runtime state | `docs/operations/RUNBOOK.md` -> `scripts/README.md` -> `mechanics/runtime-lifecycle/README.md` |
| `mechanic-change` | mechanic authors, package editors, reviewers | change a runtime package, part, owner split, local validation lane, or package card | `mechanics/README.md` -> `mechanics/<package>/README.md` -> nearest part `README.md` or `AGENTS.md` |
| `machine-fit` | host-fit editors, platform reviewers, Windows/WSL operators | handle host facts, reference platform, machine bridge, model fit, or platform adaptation | `mechanics/machine-fit/README.md` -> relevant `mechanics/machine-fit/parts/<part>/README.md` |
| `diagnostics-repair` | diagnostic editors, repair reviewers, incident handoff authors | handle read-only diagnosis, diagnostic catalogs, degradation receipts, or repair-safe closeout | `mechanics/diagnostic-spine/README.md` -> `mechanics/runtime-repair/README.md` |
| `direction-change` | roadmap editors, maintainers, release reviewers | update runtime-wide direction, horizon posture, or future trigger | `ROADMAP.md` -> `CHANGELOG.md` when release-visible -> `docs/decisions/` when rationale matters |
| `release-history` | release editors, maintainers | record release-visible history without turning it into direction or rationale | `CHANGELOG.md` -> `docs/governance/RELEASING.md` |
| `decision-rationale` | future-agent maintainers, topology editors, reviewers | explain why a durable route, owner split, workflow, validator, public contract, or topology changed | `docs/decisions/README.md` -> `docs/decisions/TEMPLATE.md` |

## First-Reading Route

The first-reading route is the shortest honest runtime overview.

Read:

1. `README.md`
2. `CHARTER.md`
3. `BOUNDARIES.md`
4. `DESIGN.md`
5. `mechanics/README.md`

This route answers:

- what the runtime substrate owns
- what must stay in AoA, ToS, sibling `aoa-*` repos, deployed runtime, or
  private machine state
- where the next package or district route begins

Stop after this route when you only need public orientation.

## Runtime-Design Route

Use this route when runtime form may move.

Read:

1. first-reading route
2. `DESIGN.md`
3. `docs/runtime/ARCHITECTURE.md`
4. `ROADMAP.md` only if the change moves runtime-wide direction
5. the package or technical district that owns the concrete surface

Runtime-design changes must not make generated, diagnostic, or live runtime
artifacts more authoritative than their source surfaces.

## Agent-Guidance Route

Use this route when root or local agent cards, agent overlays, closeout
expectations, or fast-loop lanes change.

Read:

1. `AGENTS.md`
2. `DESIGN.AGENTS.md`
3. nearest nested `AGENTS.md`
4. local README for the touched lane

Agent guidance narrows work; it does not author runtime meaning, live state, or
sibling doctrine.

## Source-Install Route

Use this route when a source checkout must create, refresh, or explain a
runtime layout.

Read:

1. first-reading route
2. `docs/runtime/PATHS.md`
3. `docs/install/DEPLOYMENT.md`
4. `mechanics/config-projection/README.md`
5. `mechanics/runtime-lifecycle/README.md`

Source-install changes must keep GitHub mirror state source/install-only. Live
`Secrets/`, `Logs/`, `Models/`, rendered private config, databases, and private
captures stay out of git.

## Runtime-Operation Route

Use this route when live operation, logs, status, smoke checks, incidents, or
operator-gated runtime checks are involved.

Read:

1. `docs/operations/RUNBOOK.md`
2. `scripts/README.md`
3. `mechanics/runtime-lifecycle/README.md`
4. `mechanics/runtime-repair/README.md` when repair posture is involved

Runtime-operation routes may inspect deployed state only when the operator
intentionally chooses that path. Source release checks use synthetic parity by
default.

## Mechanic-Change Route

Use this route when a runtime move belongs to a mechanics package or part.

Read:

1. `mechanics/README.md`
2. `mechanics/<package>/AGENTS.md`
3. `mechanics/<package>/README.md`
4. `mechanics/<package>/PARTS.md`
5. nearest part README, docs, schemas, examples, scripts, tests, or generated
   surface for the work

Mechanic-local direction, landings, provenance, legacy bridges, examples,
schemas, tests, generated artifacts, and validation ownership belong in the
package or part. Exact procedure is routed through the nearest `VALIDATION.md`,
not inherited from an agent card or root README.

## Machine-Fit Route

Use this route when host facts, reference-platform posture, platform
adaptation, machine bridge, model fit, Windows, or WSL behavior changes.

Read:

1. `mechanics/machine-fit/README.md`
2. relevant `mechanics/machine-fit/parts/<part>/README.md`
3. `docs/runtime/PATHS.md` when path mapping changes
4. `docs/operations/SECURITY.md` when host exposure or private state could be affected

`abyss-machine` remains the stronger owner of machine control-plane truth.

## Diagnostics-Repair Route

Use this route when diagnosis, diagnostic catalogs, degradation receipts,
repair-safe closeout, or repair handoff posture changes.

Read:

1. `mechanics/diagnostic-spine/README.md`
2. `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`
3. `mechanics/runtime-repair/README.md`
4. nearest diagnostic or repair part `AGENTS.md`

Diagnostic and repair surfaces are evidence and handoff routes before live
mutation authority. Exact diagnostic catalog procedure belongs in the nearest
`VALIDATION.md` and machine lane manifest, not in root README.

## Direction-Change Route

Use this route when runtime-wide direction, horizon posture, source/runtime
parity pressure, live cutover posture, machine-fit posture, diagnostic posture,
repair posture, federation consumption, mirror portability, or a concrete
future trigger changes.

Read:

1. `ROADMAP.md`
2. root `AGENTS.md` post-change route review
3. package-local `ROADMAP.md` only when the change is package-local
4. `CHANGELOG.md` when the change is release-visible
5. `docs/decisions/` when future agents need the rationale

Do not use root roadmap for package-local landing history, release history,
quest state, live runtime receipts, or private machine captures.

## Release-History Route

Use this route when public release-visible history changes.

Read:

1. `CHANGELOG.md`
2. `docs/governance/RELEASING.md`
3. `scripts/release_check.py`

Changelog entries record what changed. They do not carry future direction or
durable rationale.

## Decision-Rationale Route

Use this route after a meaningful structural, ownership, workflow, route-law,
validator-authority, public-contract, or topology change.

Read:

1. `docs/decisions/README.md`
2. `docs/decisions/AGENTS.md`
3. `docs/decisions/TEMPLATE.md`

Decision records explain why. Current source surfaces define what.

## Validation

Use `scripts/release_check.py` for broad release-facing or repo-wide
validation.

Exact current command lanes live in `docs/validation/validation_lanes.json`.
Human-executable procedure is available on demand through the nearest
`VALIDATION.md` (with root `VALIDATION.md` as the repository-wide map). Agent
cards retain route meaning, lane IDs, and stop-lines; they do not duplicate
command sequences. `scripts/README.md`, `tests/README.md`, and package-local
README/PARTS docs remain semantic ownership surfaces.

Root entry surfaces should point here or to those local authority surfaces
instead of repeating package-specific command blocks.

## Anti-Stub Rule

Do not add empty route modes, vague future labels, or compatibility names as
active topology.

A route must either:

- point to a current readable surface
- name a clear owner and stop-line
- or be deferred as a roadmap item, quest, or decision follow-up rather than
  pretending to exist

## Final Rule

The source checkout is healthy when a reader can stop early without being
deceived and go deeper without getting lost.
