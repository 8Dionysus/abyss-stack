#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

enable_now=0
while (($#)); do
  case "$1" in
    --enable-now)
      enable_now=1
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
done

unit_source="${AOA_CONFIGS_ROOT}/systemd/user/podman-compose-abyss.service"
unit_target_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
unit_target="${unit_target_dir}/podman-compose-abyss.service"

[[ -f "$unit_source" ]] || aoa_die "unit source not found: $unit_source"

mkdir -p "$unit_target_dir"
ln -sfn "$unit_source" "$unit_target"
systemctl --user daemon-reload

aoa_note "unit linked: ${unit_target}"

if ((enable_now)); then
  systemctl --user enable --now podman-compose-abyss.service
  aoa_note "unit enabled and started"
else
  aoa_note "unit reloaded but not enabled"
fi
