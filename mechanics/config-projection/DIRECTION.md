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

Near direction:

- keep render truth and bootstrap truth part-local
- keep source/runtime parity checks synthetic by default
- update validators whenever a projection source, wrapper, or runtime mirror
  expectation moves
- route federation mirror material through federation-seams instead of making
  config projection own sibling meaning
