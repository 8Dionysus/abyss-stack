#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

autonomy_mode=0
resource_guards_mode=0
service_selection_mode=0
optimization_mode=0
optimization_audit_mode=0
json_mode=0
require_complete_mode=0
selector_args=()

while (($#)); do
  case "$1" in
    --autonomy)
      autonomy_mode=1
      ;;
    --resource-guards)
      resource_guards_mode=1
      ;;
    --service-selection)
      service_selection_mode=1
      ;;
    --optimization)
      optimization_mode=1
      ;;
    --optimization-audit)
      optimization_audit_mode=1
      ;;
    --json)
      json_mode=1
      ;;
    --require-complete)
      require_complete_mode=1
      ;;
    *)
      selector_args+=("$1")
      ;;
  esac
  shift || true
done

if ((require_complete_mode && ! optimization_audit_mode)); then
  aoa_die "--require-complete requires --optimization-audit"
fi

if ((autonomy_mode)); then
  if ((json_mode)); then
    exec python "${SOURCE_ROOT}/mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py" --json
  fi
  exec python "${SOURCE_ROOT}/mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py"
fi

if ((resource_guards_mode)); then
  if ((json_mode)); then
    exec python "${SOURCE_ROOT}/mechanics/runtime-lifecycle/parts/logs-status/aoa_resource_guard_status.py" --json
  fi
  exec python "${SOURCE_ROOT}/mechanics/runtime-lifecycle/parts/logs-status/aoa_resource_guard_status.py"
fi

if ((service_selection_mode)); then
  if ((json_mode)); then
    exec python "${SOURCE_ROOT}/mechanics/runtime-lifecycle/parts/logs-status/aoa_service_selection_status.py" --json
  fi
  exec python "${SOURCE_ROOT}/mechanics/runtime-lifecycle/parts/logs-status/aoa_service_selection_status.py"
fi

if ((optimization_mode)); then
  if ((json_mode)); then
    exec python "${SOURCE_ROOT}/mechanics/runtime-lifecycle/parts/logs-status/aoa_optimization_status.py" --json
  fi
  exec python "${SOURCE_ROOT}/mechanics/runtime-lifecycle/parts/logs-status/aoa_optimization_status.py"
fi

if ((optimization_audit_mode)); then
  audit_args=()
  ((json_mode)) && audit_args+=(--json)
  ((require_complete_mode)) && audit_args+=(--require-complete)
  exec python "${SOURCE_ROOT}/mechanics/runtime-lifecycle/parts/logs-status/aoa_optimization_audit_status.py" "${audit_args[@]}"
fi

if ((json_mode)); then
  aoa_die "--json requires --autonomy, --resource-guards, --service-selection, --optimization, or --optimization-audit"
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
