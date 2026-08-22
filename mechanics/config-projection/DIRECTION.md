# Config Projection Direction

This package keeps source-authored config projection portable and public-safe.

Current posture:

- keep templates, env examples, render helpers, bootstrap helpers, and sync
  helpers visibly separated
- keep live secrets, rendered private config, and machine-local values outside
  the source checkout
- keep stable root commands as wrappers while implementation bodies live under
  package parts
- keep deployed `Configs` as a projection target, not source truth
- compose independently owned Codex hook fragments without moving their
  semantics or standalone lifecycle into the stack
- keep the Codex agent-routing relay and adapter on immutable runtime release
  paths; accept typed context only from the session/owner environment
- issue an MCP deployment receipt only from a clean exact source revision and
  exact source/deployed byte parity; keep later runtime and owner evidence
  outside the config projection claim

Near direction:

- keep render truth and bootstrap truth part-local
- keep source/runtime parity checks synthetic by default
- update validators whenever a projection source, wrapper, or runtime mirror
  expectation moves
- keep Codex-hook rendering read-only by default; require explicit atomic
  write, private backup, content-minimized receipt, and exact trust review for
  any live projection
- route federation mirror material through federation-seams instead of making
  config projection own sibling meaning
