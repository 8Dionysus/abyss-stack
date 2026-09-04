# Retire Historical Trees Without Retiring Runtime Compatibility

- Decision ID: ABYSS-STACK-D-0142
- Status: accepted
- Date: 2026-09-04
- Owner surface: `mechanics/ARTIFACT_TOPOLOGY.md`

## Index Metadata

- Original date: 2026-09-04
- Surface classes: mechanics/topology, agent/route, docs/provenance, scripts/validation
- Stack lanes: mechanics, agent guidance, validation
- Mechanic parents: agon-runtime, experience-runtime, inference-pilots, federation-seams, runtime-repair
- Guard families: source/history preservation, owner boundary, runtime compatibility
- Posture: accepted retirement rationale

## Context

Model-branded Spark guidance and historical mechanics trees compete with
current owner routes. Some old validators also require archive presence even
when active implementations have already moved into parts. History must stay
recoverable without being required in an ordinary checkout.

## Options considered

- Keep the archive and its instruction/test scaffolding in the current tree.
- Move it into another archive directory in the same checkout.
- Preserve exact Git recovery while retaining only actual current contracts.

## Decision

Retire the subtrees below. They remain at the exact original paths in the
recorded Git commit; do not add another archive district or service.

Preserve active compatibility runners under their owning parts. Quiet Bridge
CONTRACT.md consolidates the current operator, approval, and truth-status
boundary previously repeated in W5/W6 history. LOCAL_AI_TRIALS.md retains the
current compatibility mutation contract. Route validators and compilation
checks to those active surfaces, not deleted historical copies. One runner's
stale W6 source reference now names the current part contract.

Experience-runtime seed artifacts/tests and old Agon/repair notes remain
historical: their presence does not establish a current service consumer.
The federation-checks duplicate index is retired; active upstream compatibility
detail and its machine config remain unchanged. Historical placement decisions
retain their rationale; this decision supersedes local archive-presence law.

This does not remove Gemma Spark services, change runtime execution policy,
change approval gates, operate on deployed Configs, or publish a release.

## Rationale

The source tree should contain current contracts and implementation, not a
second model-branded instruction mesh or archive-only tests. Immutable Git
sources preserve provenance; active owner contracts preserve useful behavior.

## Source surfaces and recovery

Exact source commit: `a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f`. All 139 tracked blobs were verified before retirement.

| Retired subtree | Historical source | Files |
| --- | --- | ---: |
| `.agents/spark/` | [Snapshot](https://github.com/8Dionysus/abyss-stack/tree/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/.agents/spark) | 3 |
| `mechanics/agon-runtime/legacy/` | [Snapshot](https://github.com/8Dionysus/abyss-stack/tree/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/agon-runtime/legacy) | 18 |
| `mechanics/experience-runtime/legacy/` | [Snapshot](https://github.com/8Dionysus/abyss-stack/tree/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/experience-runtime/legacy) | 96 |
| `mechanics/federation-seams/parts/federation-checks/legacy/` | [Snapshot](https://github.com/8Dionysus/abyss-stack/tree/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/federation-seams/parts/federation-checks/legacy) | 2 |
| `mechanics/inference-pilots/legacy/` | [Snapshot](https://github.com/8Dionysus/abyss-stack/tree/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/inference-pilots/legacy) | 13 |
| `mechanics/runtime-repair/legacy/` | [Snapshot](https://github.com/8Dionysus/abyss-stack/tree/a4e0e0cbe7fd9c6961b733de1f06d8d62c15f02f/mechanics/runtime-repair/legacy) | 7 |

Recover a file with `git show <full-source-commit>:<original-path>`. Historical
relative links belong to the same snapshot. Normal CI does not fetch history
or recreate archives.

## Consequences

- Active contracts, runners, schemas, and owner boundaries remain checked.
- Historical investigations retrieve an exact Git source on demand.
- Canonical decision, test, validation, and KAG readers are regenerated from
  current authored sources; none is historical authority.

## Follow-up route

Validate the active source and full release lane, then review cross-owner
references before the coordinated final merge. Deployment and live consumer
acceptance remain separate and are not claimed by source validation.
