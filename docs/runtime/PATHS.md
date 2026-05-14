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
- `AOA_SOURCE_ROOT` — optional canonical source checkout root used for parity-aware helpers such as `aoa-status --autonomy`
- `AOA_WORKSPACE_ROOT` — optional shared AbyssOS workspace root for sibling repository checkouts, usually `/srv/AbyssOS`
- `AOA_AGENTS_ROOT` — optional source root used to mirror public-safe `aoa-agents` surfaces into the runtime tree
- `AOA_SKILLS_ROOT` — optional source root used by repo-local skill projection surfaces
- `AOA_ROUTING_ROOT` — optional source root used to mirror public-safe `aoa-routing` advisory surfaces into the runtime tree
- `AOA_MEMO_ROOT` — optional source root used to mirror public-safe `aoa-memo` recall and writeback-seam surfaces into the runtime tree
- `AOA_EVALS_ROOT` — optional source root used to mirror public-safe `aoa-evals` eval-selection and export-contract surfaces into the runtime tree
- `AOA_PLAYBOOKS_ROOT` — optional source root used to mirror public-safe `aoa-playbooks` activation and composition advisory surfaces into the runtime tree
- `AOA_KAG_ROOT` — optional source root used to mirror public-safe `aoa-kag` derived retrieval and regrounding surfaces into the runtime tree
- `AOA_TECHNIQUES_ROOT` — optional source root used when sibling routing checks need reusable technique surfaces
- `AOA_AOA_ROOT` — optional source root for the `Agents-of-Abyss` center repository
- `AOA_SDK_ROOT` — optional source root for SDK examples used by runtime repair dry-runs
- `AOA_TOS_ROOT` — optional source root used to mirror the source-owned `Tree-of-Sophia` handoff companion surfaces into the runtime tree
- `AOA_RUNTIME_USER` — runtime username for a few host-specific mounts
- `AOA_RUNTIME_UID` — runtime UID for a few host-specific mounts

## Fedora-first default paths

| layer | default path |
|---|---|
| default `abyss-stack` source checkout | `~/src/abyss-stack` |
| deployed runtime root | `/srv/AbyssOS/abyss-stack` |
| configs | `/srv/AbyssOS/abyss-stack/Configs` |
| secrets | `/srv/AbyssOS/abyss-stack/Secrets` |
| services | `/srv/AbyssOS/abyss-stack/Services` |
| models | `/srv/AbyssOS/abyss-stack/Models` |
| knowledge | `/srv/AbyssOS/abyss-stack/Knowledge` |
| logs | `/srv/AbyssOS/abyss-stack/Logs` |
| stack-side machine bridge logs | `/srv/AbyssOS/abyss-stack/Logs/machine-bridge` |
| codex home | `/srv/AbyssOS/abyss-stack/.codex-home` |
| optional vault | `/abyss` |
| shared AbyssOS workspace root | `/srv/AbyssOS` |
| optional `Agents-of-Abyss` source root | `/srv/AbyssOS/Agents-of-Abyss` |
| optional `Tree-of-Sophia` source root | `/srv/AbyssOS/Tree-of-Sophia` |
| optional `aoa-agents` source root | `/srv/AbyssOS/aoa-agents` |
| optional `aoa-routing` source root | `/srv/AbyssOS/aoa-routing` |
| optional `aoa-memo` source root | `/srv/AbyssOS/aoa-memo` |
| optional `aoa-evals` source root | `/srv/AbyssOS/aoa-evals` |
| optional `aoa-playbooks` source root | `/srv/AbyssOS/aoa-playbooks` |
| optional `aoa-kag` source root | `/srv/AbyssOS/aoa-kag` |
| optional `aoa-skills` source root | `/srv/AbyssOS/aoa-skills` |
| optional `aoa-techniques` source root | `/srv/AbyssOS/aoa-techniques` |
| optional `aoa-sdk` source root | `/srv/AbyssOS/aoa-sdk` |

The source checkout path is a Fedora-first default, not a universal host constant.
If the repository is intentionally relocated on another machine, set `AOA_SOURCE_ROOT` to the actual source checkout path.

The runtime-root decision is recorded in [2026-05-07 Runtime Root Under AbyssOS](../decisions/2026-05-07-runtime-root-under-abyssos.md).

Sibling repository defaults live under the same `/srv/AbyssOS` workspace root.
The older `/srv/<repo>` shape is historical compatibility only; active source
docs, examples, symlinks, and helper defaults should use `/srv/AbyssOS/<repo>`
unless a user explicitly overrides the matching environment variable.

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
- inside that Linux layer, keep the runtime root canonical as `/srv/AbyssOS/abyss-stack`

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
- `scripts/aoa-bootstrap-configs`

Parity-aware helpers such as `scripts/aoa-status --autonomy` may also use `AOA_SOURCE_ROOT` when the canonical source checkout is not under `~/src/abyss-stack`.

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
