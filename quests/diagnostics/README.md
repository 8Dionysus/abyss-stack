# diagnostics Quest Lane

Diagnostic spine and repair-handoff obligations.

Use this lane for runtime-owned diagnostic read models, reviewed diagnosis
handoffs, and bounded repair-follow-through anchors. It does not grant mutation
authority or create a free self-repair loop.

## Current state

- `done/` holds the closed diagnostic runtime packet. Drifted packets route to
  explicit repair governance only after operator intent; diagnostics still do
  not grant repair authority.
- `ready/` holds the current route-api health and closure cutover follow-up.
  It is a durable stop-line for live runtime cutover, not permission to mutate services
  from source validation.
