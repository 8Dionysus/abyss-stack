# .agents

`.agents/` contains repo-local agent surfaces that should travel with the
`abyss-stack` source checkout.

## Current Routes

- [skills](skills/AGENTS.md): thin repo-local skill install and overlay
  surfaces.
- [spark](spark/README.md): repo-local fast-loop lane for bounded
  infrastructure corrections.

## Contract

Canonical skill law stays in the owning skill repository. Local files here
should only adapt that law to source-safe `abyss-stack` runtime contracts and
current mechanics paths.

Agent model lanes belong under `.agents/<lane>/`, not as root directories.
