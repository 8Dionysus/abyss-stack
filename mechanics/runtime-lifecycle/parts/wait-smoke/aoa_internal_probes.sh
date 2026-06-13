#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AOA_SOURCE_ROOT:-$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)}"
# shellcheck source=scripts/aoa-lib.sh
source "${REPO_ROOT}/scripts/aoa-lib.sh"

strict_mode=0
profile_args=()
while (($#)); do
  case "$1" in
    --strict)
      strict_mode=1
      ;;
    *)
      profile_args+=("$1")
      ;;
  esac
  shift || true
done

aoa_parse_profile_args "${profile_args[@]}"
aoa_resolve_modules "${AOA_STACK_PROFILE}"
aoa_print_profile_summary

command -v podman >/dev/null 2>&1 || aoa_die "podman is required for internal probes"

failures=0
warnings=0
probed_any=0

has_module() {
  local target="$1"
  local module
  for module in "${AOA_PROFILE_MODULE_NAMES[@]}"; do
    [[ "$module" == "$target" ]] && return 0
  done
  return 1
}

probe_ok() {
  aoa_note "ok   $1"
}

probe_warn() {
  aoa_note "warn $1"
  warnings=$((warnings + 1))
}

probe_fail() {
  aoa_note "fail $1"
  failures=$((failures + 1))
}

container_exists() {
  local container="$1"
  podman container exists "$container" >/dev/null 2>&1
}

container_running() {
  local container="$1"
  podman inspect --format '{{.State.Status}}' "$container" 2>/dev/null || printf 'missing'
}

container_health() {
  local container="$1"
  podman inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || printf 'error'
}

probe_health_container() {
  local label="$1"
  local container="$2"
  probed_any=1

  if ! container_exists "$container"; then
    probe_fail "$label container missing: $container"
    return
  fi

  local running_status health_status
  running_status="$(container_running "$container")"
  if [[ "$running_status" != "running" ]]; then
    probe_fail "$label container not running: $running_status"
    return
  fi

  health_status="$(container_health "$container")"
  case "$health_status" in
    healthy)
      probe_ok "$label health healthy"
      ;;
    starting)
      probe_warn "$label health starting"
      ;;
    none)
      probe_warn "$label has no healthcheck"
      ;;
    *)
      probe_fail "$label health ${health_status}"
      ;;
  esac
}

probe_running_container() {
  local label="$1"
  local container="$2"
  probed_any=1

  if ! container_exists "$container"; then
    probe_fail "$label container missing: $container"
    return
  fi

  local running_status
  running_status="$(container_running "$container")"
  if [[ "$running_status" == "running" ]]; then
    probe_ok "$label running"
  else
    probe_fail "$label container not running: $running_status"
  fi
}

if has_module "51-browser-tools.yml"; then
  probe_health_container "docs-api" "docs-api"
  probe_health_container "aoa-browser" "aoa-browser"
fi

if has_module "60-monitoring.yml"; then
  probe_running_container "cadvisor" "cadvisor"
  probe_running_container "loki" "loki"
  probe_running_container "tempo" "tempo"
  probe_running_container "alloy" "alloy"
fi

if ((probed_any == 0)); then
  aoa_note "no internal-only services to probe for profile ${AOA_STACK_PROFILE}"
  exit 0
fi

if ((failures > 0)); then
  aoa_die "internal probes failed: ${failures}"
fi

if ((strict_mode)) && ((warnings > 0)); then
  aoa_die "internal probes found ${warnings} warnings in strict mode"
fi

aoa_note "internal probes passed"
if ((warnings > 0)); then
  aoa_note "warnings: ${warnings}"
fi
