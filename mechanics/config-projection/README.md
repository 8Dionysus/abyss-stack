# Config Projection Mechanic

## Mechanic card

Config projection is the mechanic for moving public-safe source templates and
operator-provided secrets into runtime-readable files without collapsing source
truth, deployed mirror, and private state.

### Trigger

Use this package when changing `config-templates/`, `env/`, render helpers,
bootstrap helpers, sync behavior, or docs about secrets and deployed `Configs`.

### abyss-stack owns

- public-safe template layout
- env example contracts
- bootstrap and sync helper behavior
- deployed config path expectations
- source/deployed separation language

### Stronger owner split

Operators own real secrets. Live host state and private captures stay outside
the source repository. Sibling repositories own the meaning of advisory surfaces
that may be mirrored into runtime config or knowledge paths.

### Inputs

Public-safe templates, env examples, explicit operator-provided secrets,
profile or preset selection, and deployment target paths.

### Outputs

Bootstrapped config files, rendered compose or service config, syncable source
surfaces, and public-safe documentation of the boundary.

### Must not claim

- templates contain live secrets
- deployed files are source truth
- sync is safe to run destructively without explicit operator intent
- config projection owns service health

### Validation

Run the commands in [AGENTS.md](AGENTS.md).

### Next route

Use [runtime-lifecycle](../runtime-lifecycle/README.md) for service activation
and [federation-seams](../federation-seams/README.md) for owner-surface mirrors.

## Active route

Current source surfaces stay in `config-templates/`, `env/`, `scripts/`, and
`mechanics/config-projection/docs/SECRETS_BOOTSTRAP.md`.

