#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

enable_now=0
restart_now=0
preset_spec=""
profile_spec=""
selection_set=0

aoa_validate_runtime_spec() {
  local label="$1"
  local value="$2"

  [[ -n "$value" ]] || return 0
  if [[ ! "$value" =~ ^[A-Za-z0-9_.-]+(,[A-Za-z0-9_.-]+)*$ ]]; then
    aoa_die "${label} must be a comma-separated list of profile or preset names"
  fi
}

aoa_append_runtime_spec() {
  local current="$1"
  local value="$2"

  if [[ -z "$current" ]]; then
    printf '%s\n' "$value"
  else
    printf '%s,%s\n' "$current" "$value"
  fi
}

while (($#)); do
  case "$1" in
    --enable-now)
      enable_now=1
      ;;
    --restart-now)
      restart_now=1
      ;;
    --preset)
      shift
      (($#)) || aoa_die "missing value after --preset"
      preset_spec="$(aoa_append_runtime_spec "$preset_spec" "$1")"
      selection_set=1
      ;;
    --preset=*)
      preset_spec="$(aoa_append_runtime_spec "$preset_spec" "${1#*=}")"
      selection_set=1
      ;;
    --profile)
      shift
      (($#)) || aoa_die "missing value after --profile"
      profile_spec="$(aoa_append_runtime_spec "$profile_spec" "$1")"
      selection_set=1
      ;;
    --profile=*)
      profile_spec="$(aoa_append_runtime_spec "$profile_spec" "${1#*=}")"
      selection_set=1
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

aoa_validate_runtime_spec "preset" "$preset_spec"
aoa_validate_runtime_spec "profile" "$profile_spec"

unit_source="${AOA_CONFIGS_ROOT}/systemd/user/podman-compose-abyss.service"
unit_target_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
unit_target="${unit_target_dir}/podman-compose-abyss.service"
selection_dropin_dir="${unit_target_dir}/podman-compose-abyss.service.d"
selection_dropin="${selection_dropin_dir}/20-runtime-selection.conf"

[[ -f "$unit_source" ]] || aoa_die "unit source not found: $unit_source"

mkdir -p "$unit_target_dir"
ln -sfn "$unit_source" "$unit_target"

if ((selection_set)); then
  mkdir -p "$selection_dropin_dir"
  {
    printf '[Service]\n'
    printf 'Environment=AOA_STACK_PRESET=%s\n' "$preset_spec"
    printf 'Environment=AOA_STACK_PROFILE=%s\n' "$profile_spec"
  } > "$selection_dropin"
  aoa_note "runtime selection drop-in: ${selection_dropin}"
  aoa_note "runtime selection preset: ${preset_spec:-(none)}"
  aoa_note "runtime selection profile: ${profile_spec:-(none)}"
fi

systemctl --user daemon-reload

aoa_note "unit linked: ${unit_target}"

if ((enable_now)); then
  systemctl --user enable --now podman-compose-abyss.service
  aoa_note "unit enabled and started"
else
  aoa_note "unit reloaded but not enabled"
fi

if ((restart_now)); then
  systemctl --user restart podman-compose-abyss.service
  aoa_note "unit restarted"
fi
