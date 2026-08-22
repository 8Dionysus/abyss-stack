# Config Projection Provenance

This package descends from the root source surfaces that describe how public
templates and operator-provided values become deployed runtime config.

The refactor pattern is:

- keep public source templates in `config-templates/`
- keep public env examples in `env/`
- keep stable operator commands in `scripts/`
- keep implementation bodies and package-owned docs under
  `mechanics/config-projection/parts/`
- keep live secrets and rendered private config out of git

## Owner Boundary

`abyss-stack` owns projection shape, template layout, wrapper behavior, and
source/runtime parity contracts. Operators own real secrets and live rendered
config. Sibling repositories own the meaning of any advisory surfaces mirrored
into runtime config. They also own the meaning and authority of their Codex
hook fragments; the stack may merge and install exact definitions but cannot
reinterpret them.

## Current Bridges

- [PARTS.md](PARTS.md) maps source districts and root wrappers to package
  parts.
- [parts/bootstrap/docs/SECRETS_BOOTSTRAP.md](parts/bootstrap/docs/SECRETS_BOOTSTRAP.md)
  describes source-safe bootstrap posture.
- [parts/rendering/docs/RENDER_TRUTH.md](parts/rendering/docs/RENDER_TRUTH.md)
  describes render authority.
- [parts/codex-hooks/README.md](parts/codex-hooks/README.md) composes native
  and owner-envelope hook definitions while preserving independent
  `aoa-memo` and `aoa-session-memory` ownership. Its stack-owned Codex-wire
  agent-routing adapter reflects the `aoa-sdk` route while leaving
  responsibility classification with `aoa-agents`.
- [docs/README.md](docs/README.md) keeps package docs as route surfaces rather
  than a second source tree.
- [../federation-seams/README.md](../federation-seams/README.md) owns sibling
  owner-surface mirror semantics.
