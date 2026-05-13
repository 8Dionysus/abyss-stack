#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

command -v rsync >/dev/null 2>&1 || aoa_die "rsync is required"

force_mode=0
while (($#)); do
  case "$1" in
    --force)
      force_mode=1
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

template_root="${SOURCE_ROOT}/config-templates"
[[ -d "$template_root" ]] || aoa_die "config template root not found: $template_root"

mkdir -p "${AOA_STACK_ROOT}/Configs" "${AOA_STACK_ROOT}/Services"

rsync_flags=(-a)
if ((force_mode)); then
  aoa_note "force mode: enabled"
else
  rsync_flags+=(--ignore-existing)
  aoa_note "force mode: disabled"
fi

aoa_note "template root: ${template_root}"
aoa_note "runtime root: ${AOA_STACK_ROOT}"

if [[ -d "${template_root}/Configs" ]]; then
  rsync "${rsync_flags[@]}" "${template_root}/Configs/" "${AOA_STACK_ROOT}/Configs/"
fi

if [[ -d "${template_root}/Services" ]]; then
  rsync "${rsync_flags[@]}" "${template_root}/Services/" "${AOA_STACK_ROOT}/Services/"
fi

aoa_note "config bootstrap complete"
aoa_note "real secrets still need to be created separately"
