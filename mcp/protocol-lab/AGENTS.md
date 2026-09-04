# AGENTS.md

## Applies to

This card applies to `mcp/protocol-lab/`.

## Role

The protocol lab is the fail-closed compatibility, currentness, and migration
gate for the production MCP wire pair used by OS Abyss. It preserves historical
fallback/lab evidence while validating the admitted modern fleet and bounded
Tasks production pair without granting new owner authority.

## Boundaries

- Production remains on the exact protocol named by the compatibility matrix.
- Release candidates, prerelease SDKs, binary literals, and successful schema
  listing are evidence inputs, not migration authority.
- Any future-protocol registration must be separately named, separately
  credentialed, disabled before prerequisites pass, and removable without
  mutating the production registration.
- The historical first pilot is `aoa-kag` read-only. Candidate and effect
  protocol probes may perform discovery only; their authority remains out of
  scope until a later decision with separate proof.
- Tasks is an extension gate and never follows automatically from core
  protocol compatibility.
- Protocol migration must not be combined with an owner-authority move.

## Validation

Validation is on-demand: use [mcp/protocol-lab/VALIDATION.md](VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

Do not edit the generated status directly. Refresh the source matrix and pair
observation, then run the builder.
