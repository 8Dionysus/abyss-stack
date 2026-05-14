# diagnostics Quest Lane

Diagnostic spine and repair-handoff obligations.

Use this lane for runtime-owned diagnostic read models, reviewed diagnosis
handoffs, and bounded repair-follow-through anchors. It does not grant mutation
authority or create a free self-repair loop.

## Current state

- `done/` holds the closed diagnostic runtime packet. Drifted packets route to
  explicit repair governance only after operator intent; diagnostics still do
  not grant repair authority.
- `done/` also holds the closed route-api health and closure cutover follow-up.
  Its closure is evidence from a reviewed operator action, not permission to
  skip future live cutover gates.
