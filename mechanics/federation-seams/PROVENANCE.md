# Federation Seams Provenance

This package descends from the runtime federation surfaces that let
`abyss-stack` consume sibling repository outputs for advisory routing,
diagnostics, and local-worker context.

The refactor pattern is:

- keep sync and check commands stable at the root wrapper surface
- keep seam-specific docs under package parts
- keep generated runtime read models under the part that builds them
- keep upstream names that are still required for compatibility in explicit
  compatibility bridges, not active topology prose
- keep routing mirror content, source identity, and trust posture explicit in
  sync and route-api status instead of inferring them from file presence
- accept SDK routing candidates only through the exact `abyss-machine`
  subject-store/trust-verdict route, with rollback and all G5 authority flags
  still false
- accept canonical SDK routing only through a distinct public-release
  `runtime` verdict and materialized owner-switch receipt; runtime rollback
  first verifies the exact predecessor manifest, ref, stable ABI, and hashes,
  then persists a compatibility-rollback marker while source ownership stays
  singular and archive authority stays false
- expose only an allowlisted trust summary through health; keep full durable
  registry records and deploy-local evidence refs behind their owner boundary

## Owner Boundary

`abyss-stack` owns runtime mirror paths, optional profile activation, route-api
consumption posture, and sync hygiene. `aoa-agents`, `aoa-memo`, `aoa-evals`,
`aoa-playbooks`, `aoa-kag`, `Tree-of-Sophia`, `Dionysus`, and other owner
repositories own the meaning of their source surfaces.

## Current Bridges

- [PARTS.md](PARTS.md) maps sibling seams to package parts.
- [parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md](parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md)
  owns active compatibility routing.
- [parts/federation-checks/docs/UPSTREAM_COMPATIBILITY_DETAIL.md](parts/federation-checks/docs/UPSTREAM_COMPATIBILITY_DETAIL.md)
  contains active detailed upstream identifier accounting.
- [parts/rpg-runtime/README.md](parts/rpg-runtime/README.md) owns RPG runtime
  projection as a read model.
- [parts/kag-seam/README.md](parts/kag-seam/README.md) owns materialization of
  the `aoa-kag` repo-self retrieval bundle into runtime stores.
- [../config-projection/README.md](../config-projection/README.md) owns
  projection of config material that feeds runtime mirrors.
- [ABYSS-STACK-D-0084](../../docs/decisions/ABYSS-STACK-D-0084-routing-mirror-provenance-readiness.md)
  records why current routing ABI fields and content/provenance/trust readiness
  are separate runtime-owner checks.
- [ABYSS-STACK-D-0085](../../docs/decisions/ABYSS-STACK-D-0085-sdk-routing-canary-intake.md)
  records why exact SDK canary readiness remains distinct from canonical
  runtime closure.
- [ABYSS-STACK-D-0086](../../docs/decisions/ABYSS-STACK-D-0086-receipt-bound-sdk-routing-cutover.md)
  records the separate two-phase canonical cutover and rollback law.
