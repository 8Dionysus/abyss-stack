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
- all core-read P1 gates are `passed`; P1-11 remains an independent Tasks
  extension gate and never blocks interpretation of the core-read verdict.

The derived status reports five separate verdicts:

- `core_read_migration_allowed`;
- `tasks_extension_allowed`;
- `candidate_migration_allowed`;
- `internal_effect_migration_allowed`;
- `external_effect_migration_allowed`.

The KAG protocol pilot can advance only the first two lab facts: whether a
read-only pilot may run and whether it completed. Candidate and effect
verdicts remain false until their own owner, proof, approval, and rollback
contracts exist.

Adapter-level proof and consumer-level proof are independent. A Python
next-era adapter may pass `server/discover`, stateless, and Abyss behavior
checks while Codex remains on the stable wire. Such a receipt advances only
the corresponding adapter gates and cannot enable registration or migration.
Likewise, an isolated read call is not the registered consumer canary.

For the first read-only pilot, `requestState` is treated as an explicit
application handle. Its minimum proof is opacity, per-request bearer
verification, principal isolation, expiry, request binding, tamper rejection,
and key-retirement revocation. Exact same-request replay may be allowed only
for a declared idempotent read result. No such allowance carries into
candidate or effect tools.

Catalog cache entries are discovery only. A private TTL bounds staleness;
`subscriptions/listen` invalidates and revokes entries while connected; a
dropped listener receives no replay and must refetch; explicit refresh is the
consumer recovery path. A tool removed at the server must remain uncallable
even while an old catalog entry is still warm. Cross-replica invalidation
requires its own production subscription-bus receipt.

Tasks remains a separately versioned extension gate. Python MCP `2.0.0` does
not implement the `2026-07-28` Tasks extension, so type literals or core
conformance cannot pass that gate.

## Dual support and rollback

`aoa_kag` remains the stable registration. `aoa_kag_next_lab` is a removable
lab alias with an independent process, loopback endpoint, credential,
`CODEX_HOME`, exact Codex binary, and exact SDK/source identity. A prerelease
consumer may prove this lab pair but cannot acquire production authority.
Rollback removes only the lab contour and then performs an actual call through
the unchanged stable operator registration.

## Claim limits

A green source validator proves the source posture and deterministic gating.
The exact final specification and stable SDK pins are source evidence. They do
not prove a modern Codex wire pair, conformance, deployed parity, registration,
canary benefit, or rollback.
