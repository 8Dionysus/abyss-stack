# Threat model

## Protected boundary

The service exposes source-owned statistical definitions and bounded derived
read models without granting arbitrary filesystem access or owner mutation.

## Controls

- Owner discovery starts from the canonical inventory.
- Workspace and port references are confined to their configured roots.
- Surface reads are limited to paths listed by an owner catalog.
- JSON payload size and preview cardinality are bounded.
- Packet checks accept JSON objects, not filesystem paths.
- The subprocess adapter uses no shell and has a timeout.
- Every MCP tool is marked read-only, non-destructive, and idempotent.
- HTTP is loopback-only and requires the owner-specific `aoa-stats` read
  bearer and scope.

## Residual risks

Owner-authored payloads may be stale, incomplete, or wrong. The service reports
their posture but cannot attest them. A same-user process that can read the
workspace or same-UID bearer credential is outside the isolation provided by this
adapter. Remote transport, write tools, raw-content reads, and validator or
refresh execution require separate owner review.
