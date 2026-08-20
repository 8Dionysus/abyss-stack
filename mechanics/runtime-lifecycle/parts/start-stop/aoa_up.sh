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

aoa_retire_legacy_ovms() {
  local compose_label container_ids container_id compose_project systemd_unit
  local -A candidate_ids=()

  command -v podman >/dev/null 2>&1 || aoa_die "podman is required to inspect the legacy OVMS owner"

  for compose_label in io.podman.compose.service com.docker.compose.service; do
    if ! container_ids="$(
      podman ps -a \
        --filter "label=${compose_label}=ovms" \
        --format '{{.ID}}'
    )"; then
      aoa_die "unable to inspect Compose-owned OVMS containers through podman"
    fi
    while IFS= read -r container_id; do
      [[ -n "$container_id" ]] && candidate_ids["$container_id"]=1
    done <<< "$container_ids"
  done

  for container_id in "${!candidate_ids[@]}"; do
    if ! compose_project="$(
      podman inspect --format '{{ index .Config.Labels "io.podman.compose.project" }}' \
        "$container_id" 2>/dev/null
    )"; then
      aoa_die "unable to inspect the Compose project for legacy OVMS container ${container_id}"
    fi
    if [[ "$compose_project" == "<no value>" || -z "$compose_project" ]]; then
      if ! compose_project="$(
        podman inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' \
          "$container_id" 2>/dev/null
      )"; then
        aoa_die "unable to inspect the Compose project for legacy OVMS container ${container_id}"
      fi
    fi
    [[ "$compose_project" == "<no value>" ]] && compose_project=""
    [[ -n "$compose_project" ]] || \
      aoa_die "legacy OVMS container ${container_id} has no Compose project identity"
    [[ "$compose_project" == "$AOA_COMPOSE_PROJECT_NAME" ]] || continue

    if ! systemd_unit="$(
      podman inspect --format '{{ index .Config.Labels "PODMAN_SYSTEMD_UNIT" }}' \
        "$container_id" 2>/dev/null
    )"; then
      aoa_die "unable to inspect the owner of legacy OVMS container ${container_id}"
    fi
    [[ "$systemd_unit" == "<no value>" ]] && systemd_unit=""
    [[ -z "$systemd_unit" ]] || \
      aoa_die "refusing to remove OVMS container ${container_id} owned by ${systemd_unit}"

    podman rm --force "$container_id" >/dev/null || \
      aoa_die "failed to retire legacy Compose OVMS container ${container_id}"
    aoa_note "retired legacy Compose OVMS container ${container_id} before socket cutover"
  done
}

if has_module "31-intel-inference.yml"; then
  # Unit linking/reload is deliberately separate from standalone secret
  # provisioning. This makes the documented first Intel launch work on a
  # fresh host while preserving the installer's fail-closed auth boundary.
  "${SCRIPTS_DIR}/aoa-install-systemd"
  "${SCRIPTS_DIR}/aoa-install-systemd" --provision-ovms-auth
  aoa_retire_legacy_ovms
  systemctl --user start abyss-ovms.socket abyss-ovms-unix.socket
  [[ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/abyss-stack/ovms.sock" ]] \
    || aoa_die "OVMS activation socket was not created; reinstall user units with aoa-install-systemd"
fi

up_args=(up -d --remove-orphans)
case "${AOA_UP_FORCE_RECREATE:-}" in
  1|true|yes|on)
    up_args+=(--force-recreate)
    ;;
esac
aoa_compose "${up_args[@]}" "${AOA_FORWARD_ARGS[@]}"
AOA_STACK_PRESET="$AOA_STACK_PRESET" AOA_STACK_PROFILE="$AOA_STACK_PROFILE" "${SCRIPTS_DIR}/aoa-warmup" || true
