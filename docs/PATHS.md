# PATHS

This document separates three things that should never be confused:

1. the source checkout path
2. the deployed runtime root
3. the optional heavy-data vault path

That separation is what allows `abyss-stack` to be Fedora-first while still usable from Windows-oriented workflows.

## Canonical variables

- `AOA_STACK_ROOT` — deployed Linux runtime root
- `AOA_CONFIGS_ROOT` — config root, usually `${AOA_STACK_ROOT}/Configs`
- `AOA_VAULT_ROOT` — optional heavy-data vault root
- `AOA_RUNTIME_USER` — runtime username for a few host-specific mounts
- `AOA_RUNTIME_UID` — runtime UID for a few host-specific mounts

## Fedora-first canonical paths

| layer | canonical path |
|---|---|
| deployed runtime root | `/srv/abyss-stack` |
| configs | `/srv/abyss-stack/Configs` |
| secrets | `/srv/abyss-stack/Secrets` |
| services | `/srv/abyss-stack/Services` |
| models | `/srv/abyss-stack/Models` |
| knowledge | `/srv/abyss-stack/Knowledge` |
| logs | `/srv/abyss-stack/Logs` |
| codex home | `/srv/abyss-stack/.codex-home` |
| optional vault | `/abyss` |

## Windows-usable path model

### Source checkout on Windows host

These are normal editing paths, not the canonical deployed runtime root:
- `C:\Users\<user>\src\abyss-stack`
- `D:\src\abyss-stack`
- any other convenient source path

### Recommended runtime model on Windows

Do **not** treat the current compose surface as a native Windows-first runtime.
Instead:
- keep the source checkout on Windows wherever convenient
- deploy the runtime inside WSL2 or a Linux-oriented Podman machine
- inside that Linux layer, keep the runtime root canonical as `/srv/abyss-stack`

### Recommended vault model on Windows

A host-side path such as:
- `D:\abyss-vault`

may be mounted into the Linux runtime as:
- `/abyss`

That preserves one stable in-runtime contract even when the host path differs.

## Deployment bridge

The repository includes helper scripts that bridge from a source checkout into the runtime tree:
- `scripts/aoa-install-layout`
- `scripts/aoa-sync-configs`

Those scripts exist to keep the separation explicit instead of relying on path confusion.

## Why not make `C:\...` the canonical runtime root?

Because the current compose surface still includes Linux-specific assumptions such as:
- rootless Podman workflows
- SELinux-oriented volume flags like `:Z`
- Linux device mounts like `/dev/dri`
- user-unit systemd lifecycle

So the right move is not to fake native parity.
The right move is to keep:
- Windows-friendly source paths
- Linux-canonical deployed runtime paths

## Practical rule

When editing docs or scripts, ask:
- is this path about source checkout?
- is this path about deployed runtime?
- is this path about the optional vault?

If those layers get mixed, drift begins.
