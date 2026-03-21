#!/usr/bin/env bash
set -euo pipefail

AOA_STACK_ROOT="${AOA_STACK_ROOT:-/srv/abyss-stack}"
AOA_CONFIGS_ROOT="${AOA_CONFIGS_ROOT:-${AOA_STACK_ROOT}/Configs}"
AOA_VAULT_ROOT="${AOA_VAULT_ROOT:-/abyss}"
AOA_STACK_PROFILE="${AOA_STACK_PROFILE:-core}"
AOA_COMPOSE_PROJECT_NAME="${AOA_COMPOSE_PROJECT_NAME:-abyss}"
AOA_LOG_TAIL="${AOA_LOG_TAIL:-200}"
AOA_WAIT_TIMEOUT_S="${AOA_WAIT_TIMEOUT_S:-120}"
AOA_WAIT_INTERVAL_S="${AOA_WAIT_INTERVAL_S:-5}"

export AOA_STACK_ROOT
export AOA_CONFIGS_ROOT
export AOA_VAULT_ROOT

AOA_MODULES_DIR="${AOA_CONFIGS_ROOT}/compose/modules"
AOA_PROFILES_DIR="${AOA_CONFIGS_ROOT}/compose/profiles"

AOA_ACTIVE_PROFILES=()
AOA_FORWARD_ARGS=()
AOA_PROFILE_NAMES=()
AOA_PROFILE_FILES=()
AOA_PROFILE_MODULE_NAMES=()
AOA_PROFILE_MODULE_FILES=()

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

aoa_expand_profile_specs() {
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

aoa_parse_profile_args() {
  local explicit_profile=0
  local profile
  local -a profile_specs=("${AOA_STACK_PROFILE}")
  local -A seen_profiles=()

  AOA_FORWARD_ARGS=()

  while (($#)); do
    case "$1" in
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

  AOA_ACTIVE_PROFILES=()
  while IFS= read -r profile; do
    [[ -n "$profile" ]] || continue
    if [[ -z "${seen_profiles[$profile]+x}" ]]; then
      seen_profiles["$profile"]=1
      AOA_ACTIVE_PROFILES+=("$profile")
    fi
  done < <(aoa_expand_profile_specs "${profile_specs[@]}")

  ((${#AOA_ACTIVE_PROFILES[@]} > 0)) || AOA_ACTIVE_PROFILES=("core")

  AOA_STACK_PROFILE="$(IFS=,; printf '%s' "${AOA_ACTIVE_PROFILES[*]}")"
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

aoa_resolve_modules() {
  local profile profile_file raw_line line trimmed module_file
  local -a profile_specs=("$@")
  local -A seen_profiles=()
  local -A seen_modules=()

  if ((${#profile_specs[@]} == 0)); then
    if ((${#AOA_ACTIVE_PROFILES[@]} > 0)); then
      profile_specs=("${AOA_ACTIVE_PROFILES[@]}")
    else
      profile_specs=("${AOA_STACK_PROFILE:-core}")
    fi
  fi

  AOA_PROFILE_NAMES=()
  AOA_PROFILE_FILES=()
  AOA_PROFILE_MODULE_NAMES=()
  AOA_PROFILE_MODULE_FILES=()

  while IFS= read -r profile; do
    [[ -n "$profile" ]] || continue
    if [[ -n "${seen_profiles[$profile]+x}" ]]; then
      continue
    fi
    seen_profiles["$profile"]=1

    profile_file="${AOA_PROFILES_DIR}/${profile}.txt"
    [[ -f "$profile_file" ]] || aoa_die "profile file not found: $profile_file"

    AOA_PROFILE_NAMES+=("$profile")
    AOA_PROFILE_FILES+=("$profile_file")

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
  done < <(aoa_expand_profile_specs "${profile_specs[@]}")

  ((${#AOA_PROFILE_NAMES[@]} > 0)) || aoa_die "no profiles resolved from specification '${AOA_STACK_PROFILE}'"
  ((${#AOA_PROFILE_MODULE_FILES[@]} > 0)) || aoa_die "resolved profiles produced zero modules"
}

aoa_compose() {
  local args=()
  local module_file

  aoa_detect_compose
  aoa_resolve_modules "${AOA_STACK_PROFILE}"

  for module_file in "${AOA_PROFILE_MODULE_FILES[@]}"; do
    args+=(-f "$module_file")
  done

  (
    cd "$AOA_CONFIGS_ROOT"
    export COMPOSE_PROJECT_NAME="$AOA_COMPOSE_PROJECT_NAME"
    "${AOA_COMPOSE_CMD[@]}" "${args[@]}" "$@"
  )
}

aoa_print_profile_summary() {
  local profile_name module_name
  aoa_note "profiles: ${AOA_STACK_PROFILE}"
  aoa_note "stack root: ${AOA_STACK_ROOT}"
  aoa_note "configs root: ${AOA_CONFIGS_ROOT}"
  aoa_note "vault root: ${AOA_VAULT_ROOT}"
  aoa_note "compose project: ${AOA_COMPOSE_PROJECT_NAME}"
  aoa_note "resolved profiles:"
  for profile_name in "${AOA_PROFILE_NAMES[@]}"; do
    aoa_note "- ${profile_name}"
  done
  aoa_note "modules:"
  for module_name in "${AOA_PROFILE_MODULE_NAMES[@]}"; do
    aoa_note "- ${module_name}"
  done
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
