#!/usr/bin/env bash
set -euo pipefail

AOA_STACK_ROOT="${AOA_STACK_ROOT:-/srv/AbyssOS/abyss-stack}"
AOA_CONFIGS_ROOT="${AOA_CONFIGS_ROOT:-${AOA_STACK_ROOT}/Configs}"
AOA_VAULT_ROOT="${AOA_VAULT_ROOT:-/abyss}"
AOA_WORKSPACE_ROOT="${AOA_WORKSPACE_ROOT:-/srv/AbyssOS}"
AOA_RUNTIME_USER="${AOA_RUNTIME_USER:-dionysus}"
AOA_RUNTIME_UID="${AOA_RUNTIME_UID:-1000}"
AOA_PODMAN_CONTAINERS_ROOT_OPERATOR_SET=0
if [[ -n "${AOA_PODMAN_CONTAINERS_ROOT+x}" ]]; then
  AOA_PODMAN_CONTAINERS_ROOT_OPERATOR_SET=1
fi
AOA_PODMAN_CONTAINERS_ROOT="${AOA_PODMAN_CONTAINERS_ROOT:-/home/${AOA_RUNTIME_USER}/.local/share/containers}"
AOA_AGENTS_ROOT="${AOA_AGENTS_ROOT:-${AOA_WORKSPACE_ROOT}/aoa-agents}"
AOA_ROUTING_ROOT="${AOA_ROUTING_ROOT:-${AOA_WORKSPACE_ROOT}/aoa-routing}"
AOA_MEMO_ROOT="${AOA_MEMO_ROOT:-${AOA_WORKSPACE_ROOT}/aoa-memo}"
AOA_EVALS_ROOT="${AOA_EVALS_ROOT:-${AOA_WORKSPACE_ROOT}/aoa-evals}"
AOA_PLAYBOOKS_ROOT="${AOA_PLAYBOOKS_ROOT:-${AOA_WORKSPACE_ROOT}/aoa-playbooks}"
AOA_KAG_ROOT="${AOA_KAG_ROOT:-${AOA_WORKSPACE_ROOT}/aoa-kag}"
AOA_TOS_ROOT="${AOA_TOS_ROOT:-${AOA_WORKSPACE_ROOT}/Tree-of-Sophia}"
AOA_OLLAMA_WARMUP_ENABLED="${AOA_OLLAMA_WARMUP_ENABLED:-false}"
AOA_OLLAMA_WARMUP_MODEL="${AOA_OLLAMA_WARMUP_MODEL:-qwen3.5:9b}"
AOA_OLLAMA_WARMUP_URL="${AOA_OLLAMA_WARMUP_URL:-http://127.0.0.1:11434}"
AOA_OLLAMA_WARMUP_WAIT_S="${AOA_OLLAMA_WARMUP_WAIT_S:-120}"
AOA_OLLAMA_WARMUP_TIMEOUT_S="${AOA_OLLAMA_WARMUP_TIMEOUT_S:-180}"
AOA_OLLAMA_WARMUP_KEEP_ALIVE="${AOA_OLLAMA_WARMUP_KEEP_ALIVE:-30m}"
AOA_OLLAMA_WARMUP_NUM_THREAD="${AOA_OLLAMA_WARMUP_NUM_THREAD:-6}"
AOA_OLLAMA_WARMUP_NUM_BATCH="${AOA_OLLAMA_WARMUP_NUM_BATCH:-32}"
AOA_OLLAMA_WARMUP_NUM_CTX="${AOA_OLLAMA_WARMUP_NUM_CTX:-}"
AOA_LLAMACPP_WARMUP_ENABLED="${AOA_LLAMACPP_WARMUP_ENABLED:-true}"
AOA_LLAMACPP_WARMUP_URL="${AOA_LLAMACPP_WARMUP_URL:-http://127.0.0.1:11435/health}"
AOA_LLAMACPP_WARMUP_WAIT_S="${AOA_LLAMACPP_WARMUP_WAIT_S:-180}"
AOA_STACK_PRESET="${AOA_STACK_PRESET:-}"
AOA_STACK_PROFILE="${AOA_STACK_PROFILE:-}"
AOA_STACK_DEFAULT_PROFILE="${AOA_STACK_DEFAULT_PROFILE:-substrate}"
AOA_COMPOSE_PROJECT_NAME="${AOA_COMPOSE_PROJECT_NAME:-abyss}"
AOA_LOG_TAIL="${AOA_LOG_TAIL:-200}"
AOA_WAIT_TIMEOUT_S="${AOA_WAIT_TIMEOUT_S:-120}"
AOA_WAIT_INTERVAL_S="${AOA_WAIT_INTERVAL_S:-5}"
AOA_EXTRA_COMPOSE_FILES="${AOA_EXTRA_COMPOSE_FILES:-}"
AOA_MACHINE_FIT_AUTO_APPLY="${AOA_MACHINE_FIT_AUTO_APPLY:-true}"
AOA_MACHINE_FIT_PATH="${AOA_MACHINE_FIT_PATH:-${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json}"

if [[ -z "${AOA_LLAMACPP_OP_OFFLOAD+x}" && -n "${AOA_LLAMACPP_NO_OP_OFFLOAD+x}" ]]; then
  case "${AOA_LLAMACPP_NO_OP_OFFLOAD}" in
    1|true|TRUE|yes|YES|on|ON)
      AOA_LLAMACPP_OP_OFFLOAD="0"
      ;;
    0|false|FALSE|no|NO|off|OFF)
      AOA_LLAMACPP_OP_OFFLOAD="1"
      ;;
    *)
      AOA_LLAMACPP_OP_OFFLOAD="${AOA_LLAMACPP_NO_OP_OFFLOAD}"
      ;;
  esac
fi

export AOA_STACK_ROOT
export AOA_CONFIGS_ROOT
export AOA_VAULT_ROOT
export AOA_WORKSPACE_ROOT
export AOA_RUNTIME_USER
export AOA_RUNTIME_UID
export AOA_PODMAN_CONTAINERS_ROOT
export AOA_AGENTS_ROOT
export AOA_ROUTING_ROOT
export AOA_MEMO_ROOT
export AOA_EVALS_ROOT
export AOA_PLAYBOOKS_ROOT
export AOA_KAG_ROOT
export AOA_TOS_ROOT
export AOA_OLLAMA_WARMUP_ENABLED
export AOA_OLLAMA_WARMUP_MODEL
export AOA_OLLAMA_WARMUP_URL
export AOA_OLLAMA_WARMUP_WAIT_S
export AOA_OLLAMA_WARMUP_TIMEOUT_S
export AOA_OLLAMA_WARMUP_KEEP_ALIVE
export AOA_OLLAMA_WARMUP_NUM_THREAD
export AOA_OLLAMA_WARMUP_NUM_BATCH
export AOA_OLLAMA_WARMUP_NUM_CTX
export AOA_LLAMACPP_WARMUP_ENABLED
export AOA_LLAMACPP_WARMUP_URL
export AOA_LLAMACPP_WARMUP_WAIT_S
export AOA_STACK_PRESET
export AOA_STACK_PROFILE
export AOA_STACK_DEFAULT_PROFILE
export AOA_EXTRA_COMPOSE_FILES
export AOA_MACHINE_FIT_AUTO_APPLY
export AOA_MACHINE_FIT_PATH
export AOA_LLAMACPP_OP_OFFLOAD

AOA_MODULES_DIR="${AOA_CONFIGS_ROOT}/compose/modules"
AOA_PROFILES_DIR="${AOA_CONFIGS_ROOT}/compose/profiles"
AOA_PRESETS_DIR="${AOA_CONFIGS_ROOT}/compose/presets"

AOA_ACTIVE_PRESETS=()
AOA_ACTIVE_PROFILES=()
AOA_FORWARD_ARGS=()
AOA_PRESET_NAMES=()
AOA_PRESET_FILES=()
AOA_PROFILE_NAMES=()
AOA_PROFILE_FILES=()
AOA_PROFILE_MODULE_NAMES=()
AOA_PROFILE_MODULE_FILES=()
AOA_EXTRA_COMPOSE_FILE_SPECS=()
AOA_EXTRA_COMPOSE_FILE_PATHS=()
AOA_MACHINE_FIT_SKIPPED_OVERLAY_SPECS=()

aoa_die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

aoa_note() {
  printf '%s\n' "$*"
}

aoa_trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

aoa_expand_specs() {
  local spec raw_part trimmed
  local -a raw_parts

  for spec in "$@"; do
    IFS=',' read -r -a raw_parts <<< "$spec"
    for raw_part in "${raw_parts[@]}"; do
      trimmed="$(aoa_trim "$raw_part")"
      [[ -n "$trimmed" ]] && printf '%s\n' "$trimmed"
    done
  done
}

aoa_join_csv() {
  local -a items=("$@")
  if ((${#items[@]} == 0)); then
    printf ''
    return
  fi
  local IFS=,
  printf '%s' "${items[*]}"
}

aoa_join_expanded_specs() {
  local spec
  local -a merged=()
  local -A seen_specs=()

  while IFS= read -r spec; do
    [[ -n "$spec" ]] || continue
    if [[ -z "${seen_specs[$spec]+x}" ]]; then
      seen_specs["$spec"]=1
      merged+=("$spec")
    fi
  done < <(aoa_expand_specs "$@")

  aoa_join_csv "${merged[@]}"
}

aoa_compose_service_names() {
  local file
  for file in "$@"; do
    [[ -f "$file" ]] || continue
    awk '
      /^services:[[:space:]]*$/ { in_services = 1; next }
      in_services && /^[^[:space:]]/ { in_services = 0 }
      in_services && /^  [A-Za-z0-9_.-]+:[[:space:]]*$/ {
        name = $1
        sub(/:$/, "", name)
        sub(/^  /, "", name)
        print name
      }
    ' "$file"
  done | sort -u
}

aoa_apply_machine_fit_runtime_posture() {
  local overlay_path overlay_spec overlay_touches record_type service_name key value
  local -a filtered_overlays=()
  local -a recommended_overlays=()
  local -A selected_services=()

  [[ "${AOA_MACHINE_FIT_AUTO_APPLY}" == "true" ]] || return 0
  [[ "${AOA_MACHINE_FIT_APPLIED:-0}" == "1" ]] && return 0
  AOA_MACHINE_FIT_APPLIED=1
  AOA_MACHINE_FIT_SKIPPED_OVERLAY_SPECS=()

  [[ -f "${AOA_MACHINE_FIT_PATH}" ]] || return 0
  command -v python3 >/dev/null 2>&1 || return 0

  while IFS=$'\t' read -r record_type key value; do
    case "$record_type" in
      SETTING)
        [[ "$key" =~ ^AOA_[A-Z0-9_]+$ ]] || continue
        if [[ -z "${!key+x}" ]] || [[ "$key" == "AOA_PODMAN_CONTAINERS_ROOT" && "${AOA_PODMAN_CONTAINERS_ROOT_OPERATOR_SET}" != "1" ]]; then
          export "${key}=${value}"
        fi
        ;;
      OVERLAY)
        [[ -n "$key" ]] && recommended_overlays+=("$key")
        ;;
    esac
  done < <(
    python3 - "${AOA_MACHINE_FIT_PATH}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

runtime = payload.get("runtime_recommendation")
if not isinstance(runtime, dict):
    raise SystemExit(0)

settings = runtime.get("validated_settings")
if isinstance(settings, dict):
    for key, value in settings.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        print(f"SETTING\t{key}\t{value}")

recommended_overlays = runtime.get("recommended_overlays")
if isinstance(recommended_overlays, list):
    for overlay in recommended_overlays:
        if isinstance(overlay, str) and overlay.strip():
            print(f"OVERLAY\t{overlay}\t")
PY
  )

  while IFS= read -r service_name; do
    [[ -n "$service_name" ]] || continue
    selected_services["$service_name"]=1
  done < <(aoa_compose_service_names "${AOA_PROFILE_MODULE_FILES[@]}")

  if ((${#recommended_overlays[@]} > 0)); then
    for overlay_spec in "${recommended_overlays[@]}"; do
      if [[ "$overlay_spec" == /* ]]; then
        overlay_path="$overlay_spec"
      else
        overlay_path="${AOA_CONFIGS_ROOT}/${overlay_spec}"
      fi

      if [[ ! -f "$overlay_path" ]]; then
        AOA_MACHINE_FIT_SKIPPED_OVERLAY_SPECS+=("$overlay_spec")
        continue
      fi

      overlay_touches=0
      while IFS= read -r service_name; do
        [[ -n "$service_name" ]] || continue
        if [[ -n "${selected_services[$service_name]+x}" ]]; then
          overlay_touches=1
          break
        fi
      done < <(aoa_compose_service_names "$overlay_path")

      if ((overlay_touches)); then
        filtered_overlays+=("$overlay_spec")
      else
        AOA_MACHINE_FIT_SKIPPED_OVERLAY_SPECS+=("$overlay_spec")
      fi
    done

    AOA_EXTRA_COMPOSE_FILES="$(aoa_join_expanded_specs "${filtered_overlays[@]}" "$AOA_EXTRA_COMPOSE_FILES")"
    export AOA_EXTRA_COMPOSE_FILES
  fi
}

# shellcheck disable=SC2120
aoa_parse_profile_args() {
  local explicit_preset=0
  local explicit_profile=0
  local item
  local -a preset_specs=()
  local -a profile_specs=()
  local -A seen_presets=()
  local -A seen_profiles=()

  if [[ -n "$AOA_STACK_PRESET" ]]; then
    preset_specs+=("$AOA_STACK_PRESET")
  fi
  if [[ -n "$AOA_STACK_PROFILE" ]]; then
    profile_specs+=("$AOA_STACK_PROFILE")
  fi

  AOA_FORWARD_ARGS=()

  while (($#)); do
    case "$1" in
      --preset)
        shift
        (($#)) || aoa_die "missing value after --preset"
        if ((explicit_preset == 0)); then
          preset_specs=()
          explicit_preset=1
        fi
        preset_specs+=("$1")
        ;;
      --preset=*)
        if ((explicit_preset == 0)); then
          preset_specs=()
          explicit_preset=1
        fi
        preset_specs+=("${1#*=}")
        ;;
      --profile)
        shift
        (($#)) || aoa_die "missing value after --profile"
        if ((explicit_profile == 0)); then
          profile_specs=()
          explicit_profile=1
        fi
        profile_specs+=("$1")
        ;;
      --profile=*)
        if ((explicit_profile == 0)); then
          profile_specs=()
          explicit_profile=1
        fi
        profile_specs+=("${1#*=}")
        ;;
      --)
        shift
        while (($#)); do
          AOA_FORWARD_ARGS+=("$1")
          shift
        done
        break
        ;;
      *)
        AOA_FORWARD_ARGS+=("$1")
        ;;
    esac
    shift || true
  done

  AOA_ACTIVE_PRESETS=()
  while IFS= read -r item; do
    [[ -n "$item" ]] || continue
    if [[ -z "${seen_presets[$item]+x}" ]]; then
      seen_presets["$item"]=1
      AOA_ACTIVE_PRESETS+=("$item")
    fi
  done < <(aoa_expand_specs "${preset_specs[@]}")

  AOA_ACTIVE_PROFILES=()
  while IFS= read -r item; do
    [[ -n "$item" ]] || continue
    if [[ -z "${seen_profiles[$item]+x}" ]]; then
      seen_profiles["$item"]=1
      AOA_ACTIVE_PROFILES+=("$item")
    fi
  done < <(aoa_expand_specs "${profile_specs[@]}")

  if ((${#AOA_ACTIVE_PRESETS[@]} == 0)) && ((${#AOA_ACTIVE_PROFILES[@]} == 0)); then
    AOA_ACTIVE_PROFILES=("$AOA_STACK_DEFAULT_PROFILE")
  fi

  AOA_STACK_PRESET="$(aoa_join_csv "${AOA_ACTIVE_PRESETS[@]}")"
  AOA_STACK_PROFILE="$(aoa_join_csv "${AOA_ACTIVE_PROFILES[@]}")"
  export AOA_STACK_PRESET
  export AOA_STACK_PROFILE
}

aoa_detect_compose() {
  if podman compose version >/dev/null 2>&1; then
    AOA_COMPOSE_CMD=(podman compose)
    return
  fi

  if command -v podman-compose >/dev/null 2>&1; then
    AOA_COMPOSE_CMD=(podman-compose)
    return
  fi

  aoa_die "neither 'podman compose' nor 'podman-compose' is available"
}

aoa_add_profile_if_new() {
  local profile="$1"
  local -n seen_profiles_ref=$2
  local profile_file

  if [[ -n "${seen_profiles_ref[$profile]+x}" ]]; then
    return
  fi
  seen_profiles_ref["$profile"]=1

  profile_file="${AOA_PROFILES_DIR}/${profile}.txt"
  [[ -f "$profile_file" ]] || aoa_die "profile file not found: $profile_file"

  AOA_PROFILE_NAMES+=("$profile")
  AOA_PROFILE_FILES+=("$profile_file")
}

aoa_resolve_profiles() {
  local preset preset_file profile raw_line line trimmed
  local -A seen_presets=()
  local -A seen_profiles=()

  if ((${#AOA_ACTIVE_PRESETS[@]} == 0)) && ((${#AOA_ACTIVE_PROFILES[@]} == 0)); then
    # shellcheck disable=SC2119
    aoa_parse_profile_args
  fi

  AOA_PRESET_NAMES=()
  AOA_PRESET_FILES=()
  AOA_PROFILE_NAMES=()
  AOA_PROFILE_FILES=()

  for preset in "${AOA_ACTIVE_PRESETS[@]}"; do
    if [[ -n "${seen_presets[$preset]+x}" ]]; then
      continue
    fi
    seen_presets["$preset"]=1

    preset_file="${AOA_PRESETS_DIR}/${preset}.txt"
    [[ -f "$preset_file" ]] || aoa_die "preset file not found: $preset_file"

    AOA_PRESET_NAMES+=("$preset")
    AOA_PRESET_FILES+=("$preset_file")

    while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
      line="${raw_line%%#*}"
      trimmed="$(aoa_trim "$line")"
      [[ -z "$trimmed" ]] && continue
      aoa_add_profile_if_new "$trimmed" seen_profiles
    done < "$preset_file"
  done

  for profile in "${AOA_ACTIVE_PROFILES[@]}"; do
    aoa_add_profile_if_new "$profile" seen_profiles
  done

  ((${#AOA_PROFILE_NAMES[@]} > 0)) || aoa_die "resolved presets/profiles produced zero profiles"
}

aoa_resolve_modules() {
  local raw_line line trimmed module_file profile_file
  local -A seen_modules=()

  aoa_resolve_profiles

  AOA_PROFILE_MODULE_NAMES=()
  AOA_PROFILE_MODULE_FILES=()

  for profile_file in "${AOA_PROFILE_FILES[@]}"; do
    while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
      line="${raw_line%%#*}"
      trimmed="$(aoa_trim "$line")"
      [[ -z "$trimmed" ]] && continue

      module_file="${AOA_MODULES_DIR}/${trimmed}"
      [[ -f "$module_file" ]] || aoa_die "module file not found: $module_file"

      if [[ -z "${seen_modules[$trimmed]+x}" ]]; then
        seen_modules["$trimmed"]=1
        AOA_PROFILE_MODULE_NAMES+=("$trimmed")
        AOA_PROFILE_MODULE_FILES+=("$module_file")
      fi
    done < "$profile_file"
  done

  ((${#AOA_PROFILE_MODULE_FILES[@]} > 0)) || aoa_die "resolved profiles produced zero modules"
  aoa_apply_machine_fit_runtime_posture
}

aoa_resolve_extra_compose_files() {
  local spec trimmed resolved
  local -A seen_files=()

  AOA_EXTRA_COMPOSE_FILE_SPECS=()
  AOA_EXTRA_COMPOSE_FILE_PATHS=()

  [[ -n "$AOA_EXTRA_COMPOSE_FILES" ]] || return 0

  while IFS= read -r spec; do
    trimmed="$(aoa_trim "$spec")"
    [[ -n "$trimmed" ]] || continue

    if [[ "$trimmed" == /* ]]; then
      resolved="$trimmed"
    else
      resolved="${AOA_CONFIGS_ROOT}/${trimmed}"
    fi

    [[ -f "$resolved" ]] || aoa_die "extra compose file not found: $resolved"

    if [[ -z "${seen_files[$resolved]+x}" ]]; then
      seen_files["$resolved"]=1
      AOA_EXTRA_COMPOSE_FILE_SPECS+=("$trimmed")
      AOA_EXTRA_COMPOSE_FILE_PATHS+=("$resolved")
    fi
  done < <(aoa_expand_specs "$AOA_EXTRA_COMPOSE_FILES")
}

aoa_compose() {
  local args=()
  local module_file extra_file

  aoa_detect_compose
  aoa_resolve_modules
  aoa_resolve_extra_compose_files

  for module_file in "${AOA_PROFILE_MODULE_FILES[@]}"; do
    args+=(-f "$module_file")
  done

  for extra_file in "${AOA_EXTRA_COMPOSE_FILE_PATHS[@]}"; do
    args+=(-f "$extra_file")
  done

  (
    cd "$AOA_CONFIGS_ROOT"
    export COMPOSE_PROJECT_NAME="$AOA_COMPOSE_PROJECT_NAME"
    "${AOA_COMPOSE_CMD[@]}" "${args[@]}" "$@"
  )
}

aoa_print_profile_summary() {
  local preset_name profile_name module_name overlay_spec

  aoa_resolve_extra_compose_files

  aoa_note "presets: ${AOA_STACK_PRESET:-(none)}"
  aoa_note "profiles: ${AOA_STACK_PROFILE:-(none)}"
  aoa_note "stack root: ${AOA_STACK_ROOT}"
  aoa_note "configs root: ${AOA_CONFIGS_ROOT}"
  aoa_note "vault root: ${AOA_VAULT_ROOT}"
  aoa_note "compose project: ${AOA_COMPOSE_PROJECT_NAME}"
  if ((${#AOA_PRESET_NAMES[@]} > 0)); then
    aoa_note "resolved presets:"
    for preset_name in "${AOA_PRESET_NAMES[@]}"; do
      aoa_note "- ${preset_name}"
    done
  fi
  aoa_note "resolved profiles:"
  for profile_name in "${AOA_PROFILE_NAMES[@]}"; do
    aoa_note "- ${profile_name}"
  done
  aoa_note "modules:"
  for module_name in "${AOA_PROFILE_MODULE_NAMES[@]}"; do
    aoa_note "- ${module_name}"
  done

  if ((${#AOA_EXTRA_COMPOSE_FILE_SPECS[@]} > 0)); then
    aoa_note "extra compose files:"
    for overlay_spec in "${AOA_EXTRA_COMPOSE_FILE_SPECS[@]}"; do
      aoa_note "- ${overlay_spec}"
    done
  fi
  if ((${#AOA_MACHINE_FIT_SKIPPED_OVERLAY_SPECS[@]} > 0)); then
    aoa_note "machine-fit overlays skipped (no selected service match):"
    for overlay_spec in "${AOA_MACHINE_FIT_SKIPPED_OVERLAY_SPECS[@]}"; do
      aoa_note "- ${overlay_spec}"
    done
  fi
}

aoa_probe_http() {
  local label="$1"
  local url="$2"
  if curl -fsS "$url" >/dev/null 2>&1; then
    aoa_note "ok   ${label} ${url}"
    return 0
  fi

  aoa_note "fail ${label} ${url}"
  return 1
}

aoa_probe_tcp() {
  local label="$1"
  local host="$2"
  local port="$3"
  if (exec 3<>"/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
    exec 3>&-
    aoa_note "ok   ${label} ${host}:${port}"
    return 0
  fi

  aoa_note "fail ${label} ${host}:${port}"
  return 1
}
