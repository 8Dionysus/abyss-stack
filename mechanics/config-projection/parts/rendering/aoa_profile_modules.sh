#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

paths_mode=0
selector_args=()
while (($#)); do
  case "$1" in
    --paths)
      paths_mode=1
      ;;
    *)
      selector_args+=("$1")
      ;;
  esac
  shift || true
done

aoa_parse_profile_args "${selector_args[@]}"
aoa_resolve_modules
aoa_print_profile_summary

if ((paths_mode)); then
  module_file=""
  aoa_note ""
  aoa_note "module files:"
  for module_file in "${AOA_PROFILE_MODULE_FILES[@]}"; do
    aoa_note "- ${module_file}"
  done
fi
