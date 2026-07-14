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

Stack-owned runtime MCP packages under `mcp/` and their root contract schemas
under `schemas/` are sync-managed too. User services launch MCP entrypoints
from deployed `Configs/mcp`, and deployed graph validators resolve
`Configs/schemas`; leaving either tree outside the projection would make a
source-green MCP change impossible to verify as live through the owner route.

The default command projects the complete public-safe allowlist. Use repeatable
`--item NAME` flags for a bounded projection and `--dry-run` to preview exact
rsync changes without creating or modifying the target:

```bash
scripts/aoa-sync-configs --dry-run --item mcp --item schemas --item systemd
scripts/aoa-sync-configs --item mcp --item schemas --item systemd
```

Unknown items and `Secrets` are rejected. Preview requires an existing target.
Source-control and interpreter/test cache material (`.git`, `__pycache__`,
pytest/mypy/ruff caches, `.coverage`, `*.pyc`) is excluded from both preview and
apply so the deployed Configs mirror contains source-managed runtime material,
not checkout residue. Sync remains non-destructive unless `--delete` is
explicitly selected.
