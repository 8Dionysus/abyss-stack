# Sync

Routes config sync helpers and deployment docs:
`scripts/aoa-sync-configs`,
`mechanics/config-projection/parts/sync/aoa_sync_configs.sh`, and
`docs/install/DEPLOYMENT.md`.

Sync owns source-to-runtime projection behavior. It must not become a Git mirror
of live private machine state.

Root public-safe route and design surfaces, including `AGENTS.md`, `DESIGN.md`,
and `DESIGN.AGENTS.md`, are synced with the source-managed `Configs` mirror.
Quest route surfaces, including `quests/` and `QUESTBOOK.md`, are also synced
because stack validation and deployed Configs self-checks use the quest surface
builder as source-managed public metadata.

Stack-owned runtime MCP packages under `mcp/`, their root contract schemas
under `schemas/`, and the stack-owned local measurement port under `stats/`
are sync-managed too. User services launch MCP entrypoints from deployed
`Configs/mcp`, deployed graph validators resolve `Configs/schemas`, and the
stats access plane resolves the stack port from `Configs/stats`; leaving any of
these trees outside the projection would make a source-green change impossible
to verify as live through the owner route.

The default command projects the complete public-safe allowlist. Use repeatable
`--item NAME` flags for a bounded projection and `--dry-run` to preview exact
rsync changes without creating or modifying the target:

```bash
scripts/aoa-sync-configs --dry-run --item mcp --item schemas --item systemd --item scripts --item mechanics
scripts/aoa-sync-configs --item mcp --item schemas --item systemd --item scripts --item mechanics
```

Include `scripts` and `mechanics` with the bounded MCP lifecycle projection so
new unit arguments and the deployed installer implementation cannot drift.
Selecting `mechanics` also projects the shared
`scripts/abyss_stack_source_identity.py` helper, because the diagnostic,
autonomy-status, and governed-runner mechanics consume that source-local
identity contract.

Unknown items and `Secrets` are rejected. Preview requires an existing target.
Source-control and interpreter/test cache material (`.git`, `__pycache__`,
pytest/mypy/ruff caches, `.coverage`, `*.pyc`) is excluded from both preview and
apply so the deployed Configs mirror contains source-managed runtime material,
not checkout residue. Sync remains non-destructive unless `--delete` is
explicitly selected.

An applying sync that includes `mcp` takes the stack-local
`Services/abyss-stack-mcp/.source-projection.lock` before the first rsync and
holds it through the complete projection. The runtime provisioner takes the
same exclusive lock before reading deployed package bytes and holds it through
runtime marker publication and environment swap. Either command fails closed
if the other transaction owns the lock. Dry-run does not take or create the
lock because it cannot mutate Configs.

An applying `mcp` sync also requires a clean Git worktree and binds the exact
source commit. After rsync, the source-owned
`scripts/mcp_deployment_manifest.py` re-hashes the complete source and deployed
`mcp/services` trees plus each package, rejects symlinks or any byte/mode
drift, and only then publishes:

```text
${AOA_STACK_ROOT}/Logs/mcp/deployments/records/<sha256>.json
${AOA_STACK_ROOT}/Logs/mcp/deployments/latest.json
```

The immutable record and atomically replaced latest reader use
`schemas/mcp-deployment-manifest.schema.json`. They bind the source revision,
each package's source revision, name and version, dependency-lock digest,
entrypoints, deployment timestamp, and exact source/deployed tree identities.
The record path is derived from the manifest body digest. Failure after rsync
leaves the deployment without a new exact receipt and the command non-zero; it
must not be admitted. A receipt proves source-to-`Configs` byte parity only.
Process, endpoint, registry, consumer schema, live call, grounding, owner
acceptance, admission, and rollback remain `not_observed` until their stronger
runtime and owner evidence exists.
