#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

autonomy_mode=0
json_mode=0
selector_args=()

while (($#)); do
  case "$1" in
    --autonomy)
      autonomy_mode=1
      ;;
    --json)
      json_mode=1
      ;;
    *)
      selector_args+=("$1")
      ;;
  esac
  shift || true
done

if ((autonomy_mode)); then
  if ((json_mode)); then
    exec python "${SOURCE_ROOT}/mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py" --json
  fi
  exec python "${SOURCE_ROOT}/mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py"
fi

if ((json_mode)); then
  aoa_die "--json requires --autonomy"
fi

aoa_parse_profile_args "${selector_args[@]}"
aoa_resolve_modules "${AOA_STACK_PROFILE}"
aoa_print_profile_summary

aoa_note ""
aoa_note "containers:"
podman ps -a --no-trunc || true

aoa_note ""
aoa_note "user unit:"
systemctl --user status podman-compose-abyss --no-pager || true
