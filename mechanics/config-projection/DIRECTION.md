# Config Projection Direction

The current contour keeps source templates public-safe and deployed config
operator-owned.

Short term:

- keep `env/*.example` and `config-templates/` easy to audit
- keep bootstrap and sync non-destructive by default
- keep secret-bearing paths out of source docs except as paths and placeholders

Next movement should map which config docs belong in this package and which stay
root operator guidance.

