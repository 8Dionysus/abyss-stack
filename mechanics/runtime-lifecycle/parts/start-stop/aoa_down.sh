#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

aoa_parse_profile_args "$@"
aoa_resolve_modules "${AOA_STACK_PROFILE}"
aoa_print_profile_summary
aoa_stop_ovms_units_if_active
aoa_compose down "${AOA_FORWARD_ARGS[@]}"
