# Experience Runtime Direction

This package makes the old experience runtime contract family convex.

Current posture:

- old named surfaces live under `legacy/`
- stronger owner doctrine stays outside this repository
- tests read package-local schemas and examples
- active package docs name the distillation stop-line instead of pretending the
  archive is active runtime

Near direction:

- keep archive contract edits paired with tests
- distill active runtime storage or worker surfaces only when one service path
  clearly consumes them
- keep old family-specific language as provenance, not current topology
- route governance, ToS, KAG, adoption meaning, and release authority back to
  the stronger owner repositories unless the stack owns a concrete transport
  or validation surface
