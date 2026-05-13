#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${AOA_SOURCE_ROOT:-$(cd -- "${script_dir}/../../../.." && pwd)}"
exec python "$repo_root/mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-w5-pilot" "$@"
