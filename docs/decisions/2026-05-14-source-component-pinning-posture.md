# Source Component Pinning Posture

Status: accepted
Date: 2026-05-14

## Context

`abyss-stack` source checkout must stay installable from GitHub while keeping
runtime component references current enough for new deployments.
Several source-managed components are stateful services with persistent data:
Postgres, Redis, Neo4j, and Qdrant. Their upstream `latest` tags can cross
major, CalVer, or storage-format lines, which is not the same risk class as
updating stateless sidecars or monitoring images.

## Options considered

1. Move every source-managed component to its absolute upstream `latest` tag.
2. Keep old digest-only pins until a live runtime migration pass is scheduled.
3. Update source-managed defaults to current reviewed `version-tag@sha256`
   references, while keeping stateful stores on the current compatible line
   unless a migration lane explicitly promotes a major jump.

## Decision

Use explicit `version-tag@sha256` references for source-managed runtime images.
For stateful datastores, update to the current compatible line in this pass:
Postgres `16.13`, Redis `7.4.9`, and Neo4j `5.26.26-community`.
Do not promote Postgres 18, Redis 8, or Neo4j 2026 CalVer as source defaults
without a separate migration and live-cutover review.

Stateless, sidecar, monitoring, and helper images may move to their current
inspected release tags when render validation remains clean.

## Rationale

Readable tags keep the mirror understandable; digests keep the install route
reproducible. Keeping stateful services on their current line avoids hiding a
data migration inside an ordinary source refresh, while still taking current
patch/security releases in that line.

The source checkout can be current without pretending that a live runtime
cutover has already happened.

## Consequences

- New source checkouts see current component pins instead of opaque stale
  digests.
- Runtime render checks can validate exact image references without pulling or
  mutating the deployed stack.
- Major stateful upgrades remain visible future work rather than accidental
  side effects.
- Operators still need a separate live migration/cutover packet before moving
  existing persistent services across major data lines.

## Source surfaces

- `compose/modules/10-storage.yml`
- `compose/modules/20-orchestration.yml`
- `compose/modules/30-local-inference.yml`
- `compose/modules/31-intel-inference.yml`
- `compose/modules/32-llamacpp-inference.yml`
- `compose/modules/40-llm-gateway.yml`
- `compose/modules/60-monitoring.yml`
- `compose/tuning/`
- `config-templates/Services/`
- `scripts/validate_stack.py`

## Follow-up route

Future major datastore upgrades belong in the runtime lifecycle and machine-fit
route: plan the source change, render it synthetically, then run a separate
operator-approved live migration/cutover packet before treating the deployed
runtime as moved.
