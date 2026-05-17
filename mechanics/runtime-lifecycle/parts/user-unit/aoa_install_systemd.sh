#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

enable_now=0
restart_now=0
link_all_user_units=0
link_system_units=0
preset_spec=""
profile_spec=""
overlay_spec=""
value=""
selection_set=0
overlay_set=0

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

aoa_validate_overlay_spec() {
  local value="$1"
  local raw_part trimmed resolved

  [[ -n "$value" ]] || return 0

  while IFS= read -r raw_part; do
    trimmed="$(aoa_trim "$raw_part")"
    [[ -n "$trimmed" ]] || aoa_die "overlay must not contain empty entries"
    if [[ ! "$trimmed" =~ ^[A-Za-z0-9_./-]+$ ]]; then
      aoa_die "overlay must be a comma-separated list of compose file paths"
    fi
    if [[ "$trimmed" == /* ]]; then
      resolved="$trimmed"
    else
      resolved="${AOA_CONFIGS_ROOT}/${trimmed}"
    fi
    [[ -f "$resolved" ]] || aoa_die "overlay compose file not found: $resolved"
  done < <(aoa_expand_specs "$value")
}

while (($#)); do
  case "$1" in
    --enable-now)
      enable_now=1
      ;;
    --restart-now)
      restart_now=1
      ;;
    --all-user-units)
      link_all_user_units=1
      ;;
    --system-units)
      link_system_units=1
      ;;
    --preset)
      shift
      (($#)) || aoa_die "missing value after --preset"
      [[ -n "$1" ]] || aoa_die "preset must not be empty"
      preset_spec="$(aoa_append_runtime_spec "$preset_spec" "$1")"
      selection_set=1
      ;;
    --preset=*)
      value="${1#*=}"
      [[ -n "$value" ]] || aoa_die "preset must not be empty"
      preset_spec="$(aoa_append_runtime_spec "$preset_spec" "$value")"
      selection_set=1
      ;;
    --profile)
      shift
      (($#)) || aoa_die "missing value after --profile"
      [[ -n "$1" ]] || aoa_die "profile must not be empty"
      profile_spec="$(aoa_append_runtime_spec "$profile_spec" "$1")"
      selection_set=1
      ;;
    --profile=*)
      value="${1#*=}"
      [[ -n "$value" ]] || aoa_die "profile must not be empty"
      profile_spec="$(aoa_append_runtime_spec "$profile_spec" "$value")"
      selection_set=1
      ;;
    --overlay|--extra-compose-file|--extra-compose-files)
      option_name="$1"
      shift
      (($#)) || aoa_die "missing value after ${option_name}"
      overlay_spec="$(aoa_append_runtime_spec "$overlay_spec" "$1")"
      overlay_set=1
      ;;
    --overlay=*|--extra-compose-file=*|--extra-compose-files=*)
      overlay_spec="$(aoa_append_runtime_spec "$overlay_spec" "${1#*=}")"
      overlay_set=1
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

aoa_validate_runtime_spec "preset" "$preset_spec"
aoa_validate_runtime_spec "profile" "$profile_spec"
if ((overlay_set)) && [[ -z "$overlay_spec" ]]; then
  aoa_die "overlay must not be empty"
fi
if ((overlay_set && ! selection_set)); then
  aoa_die "--overlay requires --preset or --profile so the full runtime shape stays explicit"
fi
aoa_validate_overlay_spec "$overlay_spec"

unit_source="${AOA_CONFIGS_ROOT}/systemd/user/podman-compose-abyss.service"
unit_manifest="${AOA_CONFIGS_ROOT}/systemd/user/managed-units.txt"
system_unit_manifest="${AOA_CONFIGS_ROOT}/systemd/system/managed-units.txt"
unit_target_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
unit_target="${unit_target_dir}/podman-compose-abyss.service"
selection_dropin_dir="${unit_target_dir}/podman-compose-abyss.service.d"
selection_dropin="${selection_dropin_dir}/20-runtime-selection.conf"
backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"

[[ -f "$unit_source" ]] || aoa_die "unit source not found: $unit_source"

aoa_link_system_unit() {
  local unit_name="$1"
  local source_path="${AOA_CONFIGS_ROOT}/systemd/system/${unit_name}"
  local target_path="/etc/systemd/system/${unit_name}"
  local backup_path
  local previous_target

  if [[ ! "$unit_name" =~ ^[A-Za-z0-9_.@-]+\.(service|timer|path)$ ]]; then
    aoa_die "invalid unit name in managed system-unit manifest: ${unit_name}"
  fi
  [[ -f "$source_path" ]] || aoa_die "managed system unit source not found: ${source_path}"

  if [[ -e "$target_path" || -L "$target_path" ]]; then
    if [[ -L "$target_path" ]]; then
      previous_target="$(readlink "$target_path" || true)"
      rm -f -- "$target_path"
      aoa_note "replacing system unit symlink with root-owned file: ${target_path} (was ${previous_target})"
    else
      backup_path="${target_path}.pre-abyss-stack-${backup_stamp}"
      cp -a -- "$target_path" "$backup_path"
      aoa_note "backup existing system unit: ${backup_path}"
    fi
  fi

  install -m 0644 -o root -g root "$source_path" "$target_path"
  aoa_note "system unit installed: ${target_path}"
}

if ((link_system_units)); then
  if ((EUID != 0)); then
    aoa_die "--system-units requires root; run via pkexec after scripts/aoa-sync-configs"
  fi
  [[ -f "$system_unit_manifest" ]] || aoa_die "managed system-unit manifest not found: ${system_unit_manifest}"
  while IFS= read -r unit_name || [[ -n "$unit_name" ]]; do
    unit_name="${unit_name%%#*}"
    unit_name="${unit_name#"${unit_name%%[![:space:]]*}"}"
    unit_name="${unit_name%"${unit_name##*[![:space:]]}"}"
    [[ -n "$unit_name" ]] || continue
    aoa_link_system_unit "$unit_name"
  done < "$system_unit_manifest"
  systemctl daemon-reload
  aoa_note "managed system units installed from ${system_unit_manifest}"
  aoa_note "system daemon reloaded; no services or timers were started, stopped, restarted, enabled, disabled, or masked"
  exit 0
fi

mkdir -p "$unit_target_dir"

aoa_link_user_unit() {
  local unit_name="$1"
  local source_path="${AOA_CONFIGS_ROOT}/systemd/user/${unit_name}"
  local target_path="${unit_target_dir}/${unit_name}"
  local backup_path
  local previous_target

  if [[ ! "$unit_name" =~ ^[A-Za-z0-9_.@-]+\.(service|timer|path)$ ]]; then
    aoa_die "invalid unit name in managed user-unit manifest: ${unit_name}"
  fi
  [[ -f "$source_path" ]] || aoa_die "managed user unit source not found: ${source_path}"

  if [[ -e "$target_path" || -L "$target_path" ]]; then
    if [[ -L "$target_path" ]]; then
      previous_target="$(readlink "$target_path" || true)"
      if [[ "$previous_target" == "$source_path" ]]; then
        aoa_note "unit already linked: ${target_path}"
        return 0
      fi
      aoa_note "relinking user unit: ${target_path} (was ${previous_target})"
    else
      backup_path="${target_path}.pre-abyss-stack-${backup_stamp}"
      cp -a -- "$target_path" "$backup_path"
      aoa_note "backup existing user unit: ${backup_path}"
    fi
  fi

  ln -sfn "$source_path" "$target_path"
  aoa_note "unit linked: ${target_path}"
}

if ((link_all_user_units)); then
  [[ -f "$unit_manifest" ]] || aoa_die "managed user-unit manifest not found: ${unit_manifest}"
  while IFS= read -r unit_name || [[ -n "$unit_name" ]]; do
    unit_name="${unit_name%%#*}"
    unit_name="${unit_name#"${unit_name%%[![:space:]]*}"}"
    unit_name="${unit_name%"${unit_name##*[![:space:]]}"}"
    [[ -n "$unit_name" ]] || continue
    aoa_link_user_unit "$unit_name"
  done < "$unit_manifest"
else
  aoa_link_user_unit "podman-compose-abyss.service"
fi

if ((selection_set || overlay_set)); then
  mkdir -p "$selection_dropin_dir"
  {
    printf '[Service]\n'
    printf 'Environment=AOA_STACK_PRESET=%s\n' "$preset_spec"
    printf 'Environment=AOA_STACK_PROFILE=%s\n' "$profile_spec"
    printf 'Environment=AOA_EXTRA_COMPOSE_FILES=%s\n' "$overlay_spec"
  } > "$selection_dropin"
  aoa_note "runtime selection drop-in: ${selection_dropin}"
  aoa_note "runtime selection preset: ${preset_spec:-(none)}"
  aoa_note "runtime selection profile: ${profile_spec:-(none)}"
  aoa_note "runtime selection overlays: ${overlay_spec:-(none)}"
fi

systemctl --user daemon-reload

if ((link_all_user_units)); then
  aoa_note "managed user units linked from ${unit_manifest}"
else
  aoa_note "single runtime unit linked: ${unit_target}"
fi

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
