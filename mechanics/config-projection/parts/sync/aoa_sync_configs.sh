#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

command -v rsync >/dev/null 2>&1 || aoa_die "rsync is required"

delete_mode=0
while (($#)); do
  case "$1" in
    --delete)
      delete_mode=1
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

mkdir -p "${AOA_CONFIGS_ROOT}"

rsync_flags=(-a)
if ((delete_mode)); then
  rsync_flags+=(--delete)
fi

aoa_note "source root: ${SOURCE_ROOT}"
aoa_note "sync target: ${AOA_CONFIGS_ROOT}"
if ((delete_mode)); then
  aoa_note "delete mode: enabled"
else
  aoa_note "delete mode: disabled"
fi

items=(
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

for item in "${items[@]}"; do
  rsync "${rsync_flags[@]}" "${SOURCE_ROOT}/${item}" "${AOA_CONFIGS_ROOT}/"
done

aoa_note "config sync complete"
