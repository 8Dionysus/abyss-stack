#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOS_GRAPH_COMMAND_NAME=tos-up exec "${MECHANIC_SCRIPT_DIR}/aoa_tos_graph.sh" "$@"
