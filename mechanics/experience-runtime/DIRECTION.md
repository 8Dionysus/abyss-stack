# Experience Runtime Direction

This package makes the old experience runtime seed family convex.

Current posture:

- old wave and `_v1` surfaces live under `legacy`
- stronger owner doctrine stays outside this repository
- tests read package-local schemas and examples
- active package docs stay small until a distillation pass exists

Near direction:

- keep legacy contract edits paired with tests
- distill active runtime storage or worker surfaces only when one service path
  clearly consumes them
- keep old seed language as provenance, not current topology

