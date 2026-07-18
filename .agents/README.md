# .agents

`.agents/` contains repo-local agent surfaces that should travel with the
`abyss-stack` source checkout.

## Current Routes

- [skills](skills/AGENTS.md): transitional projection of shared skills;
  stack-owned canonical packages live under root `skills/`.
- [spark](spark/README.md): repo-local fast-loop lane for bounded
  infrastructure corrections.

## Contract

Canonical skill law stays in the owning repository. This lane does not host a
second copy of a stack-owned package already exposed through the OS user
profile.

Agent model lanes belong under `.agents/<lane>/`, not as root directories.
