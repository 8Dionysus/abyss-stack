#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

command -v rsync >/dev/null 2>&1 || aoa_die "rsync is required"

managed_items=(
  compose
  config-templates
  docs
  mechanics
  mcp
  quests
  scripts
  schemas
  stats
  systemd
  env
  README.md
  QUESTBOOK.md
  CHARTER.md
  BOUNDARIES.md
  DESIGN.md
  DESIGN.AGENTS.md
  ROADMAP.md
  AGENTS.md
)

delete_mode=0
dry_run=0
selected_items=()
syncs_abyss_stack_mcp=0
abyss_stack_mcp_projection_lock_fd=""
source_revision=""

aoa_verify_mcp_source_snapshot() {
  local observed_revision
  observed_revision="$(git -C "$SOURCE_ROOT" rev-parse --verify HEAD)"
  [[ "$observed_revision" == "$source_revision" ]] || \
    aoa_die "MCP deployment source revision changed during synchronization"
  if [[ -n "$(git -C "$SOURCE_ROOT" status --porcelain=v1 --untracked-files=all)" ]]; then
    aoa_die "MCP deployment source worktree changed during synchronization"
  fi
}

aoa_select_sync_item() {
  local requested="$1"
  local candidate

  for candidate in "${managed_items[@]}"; do
    if [[ "$candidate" == "$requested" ]]; then
      selected_items+=("$requested")
      return 0
    fi
  done
  aoa_die "unknown sync item: ${requested}"
}

while (($#)); do
  case "$1" in
    --delete)
      delete_mode=1
      ;;
    --dry-run)
      dry_run=1
      ;;
    --item)
      shift
      (($#)) || aoa_die "missing value after --item"
      aoa_select_sync_item "$1"
      ;;
    --item=*)
      aoa_select_sync_item "${1#*=}"
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

items=("${managed_items[@]}")
if ((${#selected_items[@]})); then
  items=("${selected_items[@]}")
fi
for item in "${items[@]}"; do
  if [[ "$item" == "mcp" ]]; then
    syncs_abyss_stack_mcp=1
    break
  fi
done

if ((dry_run)); then
  [[ -d "${AOA_CONFIGS_ROOT}" ]] || aoa_die "sync target does not exist for dry-run: ${AOA_CONFIGS_ROOT}"
else
  mkdir -p "${AOA_CONFIGS_ROOT}"
fi

if ((!dry_run && syncs_abyss_stack_mcp)); then
  configs_root_without_trailing_slash="${AOA_CONFIGS_ROOT%/}"
  abyss_stack_mcp_projection_lock_root="$(
    dirname -- "$configs_root_without_trailing_slash"
  )/Services/abyss-stack-mcp"
  abyss_stack_mcp_projection_lock="${abyss_stack_mcp_projection_lock_root}/.source-projection.lock"
  if [[ -e "$abyss_stack_mcp_projection_lock_root" || \
        -L "$abyss_stack_mcp_projection_lock_root" ]]; then
    [[ -d "$abyss_stack_mcp_projection_lock_root" && \
       ! -L "$abyss_stack_mcp_projection_lock_root" ]] || \
      aoa_die "abyss-stack MCP source projection lock root must be a non-symlink directory"
  else
    install -d -m 0750 "$abyss_stack_mcp_projection_lock_root"
  fi
  if [[ -e "$abyss_stack_mcp_projection_lock" || \
        -L "$abyss_stack_mcp_projection_lock" ]]; then
    [[ -f "$abyss_stack_mcp_projection_lock" && \
       ! -L "$abyss_stack_mcp_projection_lock" ]] || \
      aoa_die "abyss-stack MCP source projection lock must be a regular non-symlink file"
  else
    (
      umask 077
      set -o noclobber
      : > "$abyss_stack_mcp_projection_lock"
    ) 2>/dev/null || true
    [[ -f "$abyss_stack_mcp_projection_lock" && \
       ! -L "$abyss_stack_mcp_projection_lock" ]] || \
      aoa_die "failed to create the abyss-stack MCP source projection lock"
  fi
  chmod 0600 "$abyss_stack_mcp_projection_lock"
  exec {abyss_stack_mcp_projection_lock_fd}<> \
    "$abyss_stack_mcp_projection_lock"
  if ! /usr/bin/flock --exclusive --nonblock \
    "$abyss_stack_mcp_projection_lock_fd"; then
    aoa_die "abyss-stack MCP runtime provisioning holds the source projection lock"
  fi
  command -v git >/dev/null 2>&1 || \
    aoa_die "git is required for MCP deployment provenance"
  command -v python3 >/dev/null 2>&1 || \
    aoa_die "python3 is required for MCP deployment provenance"
  source_revision="$(git -C "$SOURCE_ROOT" rev-parse --verify HEAD)"
  [[ "$source_revision" =~ ^[0-9a-f]{40}$ ]] || \
    aoa_die "MCP deployment requires one exact source commit"
  aoa_verify_mcp_source_snapshot
fi

rsync_flags=(
  -a
  --exclude=.git/
  --exclude=__pycache__/
  --exclude=.pytest_cache/
  --exclude=.mypy_cache/
  --exclude=.ruff_cache/
  --exclude=.coverage
  --exclude='*.pyc'
)
if ((delete_mode)); then
  rsync_flags+=(--delete)
fi
if ((dry_run)); then
  rsync_flags+=(--dry-run --itemize-changes)
fi

aoa_note "source root: ${SOURCE_ROOT}"
aoa_note "sync target: ${AOA_CONFIGS_ROOT}"
if ((delete_mode)); then
  aoa_note "delete mode: enabled"
else
  aoa_note "delete mode: disabled"
fi
aoa_note "dry-run: $([[ $dry_run -eq 1 ]] && printf enabled || printf disabled)"
aoa_note "selected items: ${items[*]}"

for item in "${items[@]}"; do
  rsync "${rsync_flags[@]}" "${SOURCE_ROOT}/${item}" "${AOA_CONFIGS_ROOT}/"
done

if ((dry_run)); then
  aoa_note "config sync preview complete; no files changed"
else
  if ((syncs_abyss_stack_mcp)); then
    aoa_verify_mcp_source_snapshot
    deployment_manifest_command=(
      python3
      "${MECHANIC_SCRIPT_DIR}/scripts/mcp_deployment_manifest.py"
      --source-root
      "${SOURCE_ROOT}"
      --deployed-root
      "${AOA_CONFIGS_ROOT}"
      --output-root
      "${AOA_STACK_ROOT}/Logs/mcp/deployments"
      --source-revision
      "${source_revision}"
    )
    if ((delete_mode)); then
      deployment_manifest_command+=(--delete-mode)
    fi
    "${deployment_manifest_command[@]}"
  fi
  aoa_note "config sync complete"
fi
if [[ -n "$abyss_stack_mcp_projection_lock_fd" ]]; then
  exec {abyss_stack_mcp_projection_lock_fd}>&-
fi
