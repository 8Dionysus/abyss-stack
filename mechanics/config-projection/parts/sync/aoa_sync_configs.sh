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

if ((dry_run)); then
  [[ -d "${AOA_CONFIGS_ROOT}" ]] || aoa_die "sync target does not exist for dry-run: ${AOA_CONFIGS_ROOT}"
else
  mkdir -p "${AOA_CONFIGS_ROOT}"
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
  aoa_note "config sync complete"
fi
