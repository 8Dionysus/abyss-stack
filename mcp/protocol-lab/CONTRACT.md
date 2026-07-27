# Protocol Migration Contract

## Inputs

The lab consumes:

1. an exact stable specification revision;
2. an exact next specification revision and release status;
3. exact stable and next SDK revisions;
4. an exact official conformance-suite revision;
5. an observed consumer version and pair-level evidence;
6. Abyss-specific conformance, canary, dual-support, and rollback receipts.

Every drift trigger invalidates the current observation until it is refreshed.
Protocol strings discovered inside a binary are navigation evidence only.

## Admission

Production migration is allowed only when:

- the next specification is final and production-allowed;
- a stable, production-allowed SDK supports its wire version;
- Codex and the exact server pair are observed on that wire;
- `server/discover`, stateless behavior, explicit handles, and trace/cache
  behavior are observed;
- official and Abyss pair-conformance pass;
- compatibility aliases, dual support, and rollback pass;
- the isolated read-only `aoa-kag` canary passes;
- all P1 gates are `passed`.

The derived status always reports `effectful_migration_allowed=false`.
Effectful migration requires a later, separate contract.

## Dual support and rollback

`aoa_kag` remains the stable registration. `aoa_kag_next_lab` is an independent
lab alias and is disabled in the pre-final source posture. It must use an
independent process and credential contour. Rollback removes only the lab
alias and then revalidates the unchanged stable pair and schema digest.

## Claim limits

A green source validator proves the source posture and deterministic gating.
It does not prove final publication, SDK stability, a live Codex wire pair,
conformance, deployed parity, registration, canary benefit, or rollback.
