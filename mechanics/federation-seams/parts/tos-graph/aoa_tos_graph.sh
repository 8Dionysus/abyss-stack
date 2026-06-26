#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
command_name="${TOS_GRAPH_COMMAND_NAME:-aoa-tos-graph}"

usage() {
  cat <<EOF
Usage: ${command_name} [--no-open] [--open] [--no-wait] [--force-start] [--status] [--down] [--] [compose args...]

Start the Tree of Sophia graph review workbench through the curation profile,
wait for the curation profile, and open it when a desktop opener is available.

Options:
  --open       Try to open the UI after startup. This is the default.
  --no-open    Start and print the UI URL without opening a browser.
  --no-wait    Do not wait for the health endpoint after startup.
  --force-start Run compose even when the workbench is already reachable.
  --status     Do not start containers; report the current health endpoint.
  --down       Stop the curation profile instead of starting it.
  -h, --help   Show this help.
EOF
}

open_requested=1
wait_requested=1
status_only=0
down_requested=0
force_start=0
forward_args=()

while (($#)); do
  case "$1" in
    --open)
      open_requested=1
      ;;
    --no-open)
      open_requested=0
      ;;
    --no-wait)
      wait_requested=0
      ;;
    --status)
      status_only=1
      ;;
    --force-start)
      force_start=1
      ;;
    --down)
      down_requested=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while (($#)); do
        forward_args+=("$1")
        shift
      done
      break
      ;;
    *)
      forward_args+=("$1")
      ;;
  esac
  shift || true
done

host_port="${AOA_TOS_GRAPH_HOST_PORT:-5410}"
ui_url="http://127.0.0.1:${host_port}/"
health_url="http://127.0.0.1:${host_port}/health"

check_health() {
  command -v python3 >/dev/null 2>&1 || return 1
  python3 - "$health_url" <<'PY'
from __future__ import annotations

import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
        raise SystemExit(0 if response.status < 500 else 1)
except Exception:
    raise SystemExit(1)
PY
}

wait_for_profile() {
  AOA_STACK_PRESET="" AOA_STACK_PROFILE="" "${SCRIPTS_DIR}/aoa-wait" --profile curation >/dev/null
}

profile_ready() {
  AOA_STACK_PRESET="" AOA_STACK_PROFILE="" "${SCRIPTS_DIR}/aoa-smoke" --profile curation >/dev/null 2>&1
}

open_ui() {
  [[ "$open_requested" == "1" ]] || return 0
  case "${AOA_TOS_GRAPH_OPEN:-true}" in
    1|true|TRUE|yes|YES|on|ON)
      ;;
    *)
      return 0
      ;;
  esac

  if command -v xdg-open >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    nohup xdg-open "$ui_url" >/dev/null 2>&1 || true
    return 0
  fi
  if command -v open >/dev/null 2>&1; then
    open "$ui_url" >/dev/null 2>&1 || true
  fi
}

if ((down_requested)); then
  AOA_STACK_PRESET="" AOA_STACK_PROFILE="" "${SCRIPTS_DIR}/aoa-down" --profile curation "${forward_args[@]}"
  printf 'ToS graph curation profile stopped\n'
  exit 0
fi

if ((status_only)); then
  if check_health; then
    printf 'ToS graph is reachable: %s\n' "$ui_url"
    exit 0
  fi
  printf 'ToS graph is not reachable: %s\n' "$health_url" >&2
  exit 1
fi

printf 'Starting ToS graph review workbench through profile: curation\n'
if ((force_start == 0)) && profile_ready; then
  printf 'ToS graph curation profile is already reachable: %s\n' "$ui_url"
else
  AOA_STACK_PRESET="" AOA_STACK_PROFILE="" "${SCRIPTS_DIR}/aoa-up" --profile curation "${forward_args[@]}"
fi

if ((wait_requested)); then
  printf 'Waiting for ToS graph curation profile: %s\n' "$health_url"
  if ! wait_for_profile; then
    printf 'error: timed out waiting for ToS graph curation profile: %s\n' "$health_url" >&2
    exit 1
  fi
fi

printf 'ToS graph UI: %s\n' "$ui_url"
printf 'Switch views, layers, clusters, nodes, review packets, snapshots, audit, paths, and search inside the left rail.\n'
open_ui
