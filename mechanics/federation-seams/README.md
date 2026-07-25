# Federation Seams Mechanic

## Mechanic card

Federation seams are the mechanic for letting runtime consume public-safe owner
surfaces from sibling repositories without absorbing their authority.

### Trigger

Use this package when changing federation sync, advisory knowledge mirrors,
route-api posture, sibling repository seam docs, or optional federation
profiles.

### abyss-stack owns

- runtime mirror paths
- sync wrappers and checks
- profile and preset activation shape
- advisory service plumbing
- public-safe runtime seam documentation

### Stronger owner split

`aoa-agents`, `aoa-memo`, `aoa-evals`, `aoa-playbooks`, `aoa-kag`,
`Tree-of-Sophia`, and other owner repositories own their source meaning.
`abyss-stack` owns only runtime consumption and mirror hygiene.

### Inputs

Public-safe owner surfaces, explicit profile selection, sync layer names,
runtime config, and route-api or advisory service state.

### Outputs

Synced runtime mirrors, advisory inputs, provenance-aware health checks, and
clear owner-boundary docs. Routing health distinguishes file presence,
consumer compatibility, source/content provenance, and trust admission instead
of collapsing them into one presence flag. The SDK succession route additionally
distinguishes an exact trust-admitted `canary_ready` mirror from canonical
`closure_ready` runtime state.

### Must not claim

- mirrored content is owner acceptance
- advisory routes are proof
- federation is active when the profile is absent
- runtime can rewrite sibling owner truth

### Validation

Run the commands in [AGENTS.md](AGENTS.md).

### Next route

Use [config-projection](../config-projection/README.md) for mirror config and
[governed-execution](../governed-execution/README.md) when advisory input feeds
local-worker behavior.

## Active route

Current source surfaces stay under the owning `parts/` routes, root federation
wrappers, compose modules, and config templates.
RPG runtime read-model schemas and examples live in
`mechanics/federation-seams/parts/rpg-runtime/`, their source-generated transport
files live in `mechanics/federation-seams/parts/rpg-runtime/generated/`, and their script
coverage lives in `mechanics/federation-seams/parts/rpg-runtime/tests/`.
