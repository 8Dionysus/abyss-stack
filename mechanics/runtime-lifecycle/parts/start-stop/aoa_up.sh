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

has_module() {
  local target="$1"
  local module
  for module in "${AOA_PROFILE_MODULE_NAMES[@]}"; do
    [[ "$module" == "$target" ]] && return 0
  done
  return 1
}

if has_module "31-intel-inference.yml"; then
  "${SCRIPTS_DIR}/aoa-install-systemd" --provision-ovms-auth
  systemctl --user start abyss-ovms.socket abyss-ovms-unix.socket
  [[ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/abyss-stack/ovms.sock" ]] \
    || aoa_die "OVMS activation socket was not created; reinstall user units with aoa-install-systemd"
fi

up_args=(up -d)
case "${AOA_UP_FORCE_RECREATE:-}" in
  1|true|yes|on)
    up_args+=(--force-recreate)
    ;;
esac
aoa_compose "${up_args[@]}" "${AOA_FORWARD_ARGS[@]}"
AOA_STACK_PRESET="$AOA_STACK_PRESET" AOA_STACK_PROFILE="$AOA_STACK_PROFILE" "${SCRIPTS_DIR}/aoa-warmup" || true
