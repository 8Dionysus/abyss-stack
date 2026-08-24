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
- `AOA_SOURCE_ROOT` — optional explicit source checkout lookup coordinate used for parity-aware helpers such as `aoa-status --autonomy`; when set, it must be paired with `AOA_SOURCE_IDENTITY`
- `AOA_SOURCE_IDENTITY` — absolute JSON receipt for the explicit source root, using `abyss_stack_source_identity_v1` with exact Git `HEAD`/tree coordinates, selected source-surface SHA-256 digests, and a content seal; a shared receipt covers all three parity-aware consumers
- `AOA_WORKSPACE_ROOT` — optional shared AbyssOS workspace root for sibling repository checkouts, usually `/srv/AbyssOS`
- `AOA_AGENTS_ROOT` — optional source root used to mirror public-safe `aoa-agents` surfaces into the runtime tree
- `AOA_SKILLS_ROOT` — optional source root used by repo-local skill projection surfaces
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
- `AOA_PODMAN_CONTAINERS_ROOT` — rootless Podman containers storage root for
  observability mounts; the `aoa-*` shell route defaults it to
  `/home/${AOA_RUNTIME_USER}/.local/share/containers`

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
| repo-self KAG runtime | `/srv/AbyssOS/abyss-stack/Knowledge/kag/repo-self` |
| logs | `/srv/AbyssOS/abyss-stack/Logs` |
| stack-side machine bridge logs | `/srv/AbyssOS/abyss-stack/Logs/machine-bridge` |
| stack MCP policy audit journals | `/srv/AbyssOS/abyss-stack/Logs/mcp/audit` |
| codex home | `/srv/AbyssOS/abyss-stack/.codex-home` |
| Codex agent-routing install root | `/srv/AbyssOS/abyss-stack/.codex-home/agent-tool-routing` |
| optional vault | `/abyss` |
| shared AbyssOS workspace root | `/srv/AbyssOS` |
| optional `Agents-of-Abyss` source root | `/srv/AbyssOS/Agents-of-Abyss` |
| optional `Tree-of-Sophia` source root | `/srv/AbyssOS/Tree-of-Sophia` |
| optional `aoa-agents` source root | `/srv/AbyssOS/aoa-agents` |
| optional `aoa-memo` source root | `/srv/AbyssOS/aoa-memo` |
| optional `aoa-evals` source root | `/srv/AbyssOS/aoa-evals` |
| optional `aoa-playbooks` source root | `/srv/AbyssOS/aoa-playbooks` |
| optional `aoa-kag` source root | `/srv/AbyssOS/aoa-kag` |
| optional `aoa-skills` source root | `/srv/AbyssOS/aoa-skills` |
| optional `aoa-techniques` source root | `/srv/AbyssOS/aoa-techniques` |
| optional `aoa-sdk` source root | `/srv/AbyssOS/aoa-sdk` |

The source checkout path is a Fedora-first default, not a universal host constant.
`AOA_SOURCE_ROOT` is only a lookup coordinate: an explicit binding is admitted
only with an `AOA_SOURCE_IDENTITY` receipt whose content seal covers the target,
exact Git `HEAD`/tree, and selected source surfaces. A source candidate must
also have the source shape, the first non-empty `README.md` line exactly
`# abyss-stack`, and the exact line 'Root route card for `abyss-stack`.' within
the first eight `AGENTS.md` lines.

Parity-aware helpers do not search `~/src/abyss-stack`, sibling checkouts, or
the workspace root as an implicit fallback. When a helper runs from an
owner-qualified source checkout, it derives the same content-addressed identity
from that executing root, which preserves legitimate isolated worktrees without
making a canonical-path claim. Relative paths, `/proc/self/cwd`, and symlink
aliases are accepted only when they resolve to a root covered by the explicit
identity contract; invalid explicit input never falls back. Each consumer
revalidates the content identity and source-root device/inode before source use,
and source admission rejects fixture-only roots plus symlinked required
topology. Autonomy parity opens its validator from the pinned root through an
inherited descriptor, then revalidates to detect post-open replacement; the
revalidation is not an atomic TOCTOU claim. Governed Git/worktree operations
pin the root cwd and sanitize inherited `GIT_*` configuration. The governed
runner follows the same rule and does not promote policy
`default_repo_root` or `STACK_ROOT` into source authority. This source binding
does not prove remote currentness, deployment, runtime health, or semantic
acceptance.

The runtime-root decision is recorded in [2026-05-07 Runtime Root Under AbyssOS](../decisions/ABYSS-STACK-D-0001-runtime-root-under-abyssos.md).

Sibling repository defaults live under the same `/srv/AbyssOS` workspace root.
The older `/srv/<repo>` shape is historical compatibility only; active source
docs, examples, symlinks, and helper defaults should use `/srv/AbyssOS/<repo>`
unless a user explicitly overrides the matching environment variable.

The stable runtime namespace
`Knowledge/federation/aoa-routing/` is not a source checkout. It is
materialized only from a receipt-bound, admitted `aoa-sdk` release through
`scripts/aoa-routing-cutover`. Ordinary federation sync may inspect that
materialization but cannot produce or repair it.

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

Parity-aware helpers such as `scripts/aoa-status --autonomy` use the explicit
`AOA_SOURCE_ROOT` plus `AOA_SOURCE_IDENTITY` binding when the source checkout is
not the running source checkout. The deployed `Configs` projection is never
treated as source authority, and an absent or invalid binding remains an
explicit truth gap.

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
