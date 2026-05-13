#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
SMOKE_SCRIPT="${SCRIPTS_DIR}/aoa-smoke"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

aoa_parse_profile_args "$@"

timeout_s="${AOA_WAIT_TIMEOUT_S:-120}"
interval_s="${AOA_WAIT_INTERVAL_S:-5}"
deadline=$((SECONDS + timeout_s))

while ((SECONDS < deadline)); do
  if AOA_STACK_PRESET="$AOA_STACK_PRESET" AOA_STACK_PROFILE="$AOA_STACK_PROFILE" "$SMOKE_SCRIPT" "${AOA_FORWARD_ARGS[@]}" >/dev/null 2>&1; then
    printf 'profile selection is ready\n'
    exit 0
  fi
  sleep "$interval_s"
done

printf 'error: timeout waiting for profile selection\n' >&2
exit 1
