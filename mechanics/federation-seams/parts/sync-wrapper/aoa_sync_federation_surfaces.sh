#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)"
# shellcheck source=scripts/aoa-lib.sh
source "${REPO_ROOT}/scripts/aoa-lib.sh"

command -v python3 >/dev/null 2>&1 || aoa_die "python3 is required"

layers=()
check_mode=0
json_mode=0
sync_if_stale=0
while (($#)); do
  case "$1" in
    --check)
      check_mode=1
      ;;
    --json)
      json_mode=1
      ;;
    --sync-if-stale)
      sync_if_stale=1
      ;;
    --layer)
      shift || true
      (($#)) || aoa_die "missing value after --layer"
      layers+=("$1")
      ;;
    --layer=*)
      layers+=("${1#*=}")
      ;;
    *)
      aoa_die "unknown argument: $1"
      ;;
  esac
  shift || true
  done

(( ${#layers[@]} > 0 )) || aoa_die "expected --layer"

if (( json_mode )) && ! (( check_mode )); then
  aoa_die "--json requires --check"
fi
if (( sync_if_stale )) && ! (( check_mode )); then
  aoa_die "--sync-if-stale requires --check"
fi

emit_check_json() {
  local layer="$1"
  local status="$2"
  local source_root="$3"
  local mirror_target="$4"
  local source_commit="$5"
  local mirror_commit="$6"
  local mirror_generated_at_utc="$7"
  local refresh_command="$8"
  local sync_recommended="$9"
  local synced="${10}"
  local freshness_status="${11}"
  local manifest_path="${12}"
  shift 12
  python3 - "$layer" "$status" "$source_root" "$mirror_target" \
    "$source_commit" "$mirror_commit" "$mirror_generated_at_utc" "$refresh_command" \
    "$sync_recommended" "$synced" "$freshness_status" "$manifest_path" "$@" <<'PY'
from pathlib import Path
import json
import sys

layer = sys.argv[1]
status = sys.argv[2]
source_root = str(Path(sys.argv[3])) if sys.argv[3] else None
mirror_target = str(Path(sys.argv[4]))
source_commit = sys.argv[5] or None
mirror_commit = sys.argv[6] or None
mirror_generated_at_utc = sys.argv[7] or None
refresh_command = sys.argv[8] or None
sync_recommended = sys.argv[9] == "true"
synced = sys.argv[10] == "true"
freshness_status = sys.argv[11] or status
manifest_path = str(Path(sys.argv[12]))
missing_files = [str(Path(item)) for item in sys.argv[13:]]

print(
    json.dumps(
        {
            "layer": layer,
            "status": status,
            "source_root": source_root,
            "mirror_target": mirror_target,
            "manifest_path": manifest_path,
            "freshness_status": freshness_status,
            "source_git_commit": source_commit,
            "mirror_source_git_commit": mirror_commit,
            "mirror_generated_at_utc": mirror_generated_at_utc,
            "refresh_command": refresh_command,
            "sync_recommended": sync_recommended,
            "synced": synced,
            "missing_files": missing_files,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
)
PY
}

git_commit_for_root() {
  local root="$1"
  [[ -e "${root}/.git" ]] || return 0
  git -C "$root" rev-parse HEAD 2>/dev/null || true
}

read_manifest_metadata() {
  local manifest_path="$1"
  local layer="$2"
  local target_root="$3"
  shift 3
  python3 - "$manifest_path" "$layer" "$target_root" "$@" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

manifest_path = Path(sys.argv[1])
layer = sys.argv[2]
target_root = Path(sys.argv[3])
required_files = list(sys.argv[4:])
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
if payload.get("schema") != "abyss_stack_federation_mirror_manifest_v1":
    raise SystemExit("invalid federation mirror manifest schema")
if payload.get("layer") != layer:
    raise SystemExit("federation mirror manifest layer mismatch")
if payload.get("mirror_is_authority") is not False:
    raise SystemExit("federation mirror manifest must deny mirror authority")
if payload.get("required_file_count") != len(required_files):
    raise SystemExit("federation mirror manifest required-file count mismatch")
if payload.get("required_files") != required_files:
    raise SystemExit("federation mirror manifest required-file list mismatch")
file_sha256 = payload.get("file_sha256")
if not isinstance(file_sha256, dict) or set(file_sha256) != set(required_files):
    raise SystemExit("federation mirror manifest content-hash set mismatch")
for rel_path in required_files:
    path = target_root / rel_path
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_sha256.get(rel_path) != actual:
        raise SystemExit(f"federation mirror content hash mismatch: {rel_path}")
for key in ("source_git_commit", "generated_at_utc", "refresh_command"):
    value = payload.get(key)
    if value is None:
        print("")
    elif isinstance(value, str):
        print(value)
    else:
        raise SystemExit(f"invalid manifest field {key}: {value!r}")
PY
}

resolve_federation_config_dir() {
  local source_templates_dir runtime_configs_dir
  source_templates_dir="${REPO_ROOT}/config-templates/Configs/federation"
  runtime_configs_dir="${AOA_CONFIGS_ROOT}/federation"

  if [[ -d "${source_templates_dir}" ]]; then
    printf '%s\n' "${source_templates_dir}"
    return 0
  fi
  if [[ -d "${runtime_configs_dir}" ]]; then
    printf '%s\n' "${runtime_configs_dir}"
    return 0
  fi
  aoa_die "federation config directory not found"
}

load_required_paths() {
  local config_path="$1"
  python3 - "$config_path" <<'PY'
from pathlib import Path
import sys

import yaml

config_path = Path(sys.argv[1])
payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
required_files = payload.get("required_files")
if not isinstance(required_files, list) or not required_files:
    raise SystemExit(f"required_files missing or empty in {config_path}")
for rel_path in required_files:
    if not isinstance(rel_path, str) or not rel_path:
        raise SystemExit(f"invalid required_files entry in {config_path}: {rel_path!r}")
    print(rel_path)
PY
}

load_bridge_runtime_evidence_refs() {
  local config_dir="$1"
  python3 - "$config_dir/upstream-compatibility-bridge.json" <<'PY'
from pathlib import Path
import json
import sys

bridge_path = Path(sys.argv[1])
payload = json.loads(bridge_path.read_text(encoding="utf-8"))
templates = payload.get("runtime_evidence_templates")
if not isinstance(templates, dict):
    raise SystemExit(f"runtime_evidence_templates missing or invalid in {bridge_path}")
for name, template in templates.items():
    if not isinstance(template, dict):
        raise SystemExit(f"invalid runtime evidence template bridge entry: {name!r}")
    upstream_ref = template.get("upstream_source_ref")
    if not isinstance(upstream_ref, str) or not upstream_ref:
        raise SystemExit(f"upstream_source_ref missing for runtime evidence template bridge entry: {name}")
    print(upstream_ref)
PY
}

load_bridge_playbook_automation_ref() {
  local config_dir="$1"
  python3 - "$config_dir/upstream-compatibility-bridge.json" <<'PY'
from pathlib import Path
import json
import sys

bridge_path = Path(sys.argv[1])
payload = json.loads(bridge_path.read_text(encoding="utf-8"))
bridge = payload.get("playbook_automation_plans")
if not isinstance(bridge, dict):
    raise SystemExit(f"playbook_automation_plans missing or invalid in {bridge_path}")
upstream_rel_path = bridge.get("upstream_rel_path")
if not isinstance(upstream_rel_path, str) or not upstream_rel_path:
    raise SystemExit(f"playbook automation upstream_rel_path missing in {bridge_path}")
print(upstream_rel_path)
PY
}

check_canonical_routing_layer() {
  local synced="${1:-false}"
  local emit="${2:-true}"
  local target_root manifest_path config_dir config_path inspection
  local source_commit mirror_generated_at_utc refresh_command status freshness_status
  local -a routing_fields=() routing_manifest_fields=()
  target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-routing"
  manifest_path="${target_root}/manifest/federation_mirror_manifest.json"
  config_dir="$(resolve_federation_config_dir)"
  config_path="${config_dir}/aoa-routing.yaml"
  refresh_command="scripts/aoa-routing-cutover materialize --explicit-exact-inputs"
  source_commit=""
  mirror_generated_at_utc=""
  status="ok"
  freshness_status="sdk_canonical_materialized"

  if inspection="$(
    "${REPO_ROOT}/scripts/aoa-routing-cutover" inspect-materialized \
      --target-root "${target_root}" \
      --routing-config "${config_path}"
  )"; then
    mapfile -t routing_fields < <(
      python3 - "${inspection}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(payload.get("sdk_source_ref") or "")
PY
    )
    source_commit="${routing_fields[0]:-}"
    if [[ -f "${manifest_path}" ]]; then
      mapfile -t routing_manifest_fields < <(
        python3 - "${manifest_path}" <<'PY'
from pathlib import Path
import json
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload.get("generated_at_utc") or "")
print(payload.get("refresh_command") or "")
PY
      )
      mirror_generated_at_utc="${routing_manifest_fields[0]:-}"
      refresh_command="${routing_manifest_fields[1]:-${refresh_command}}"
    fi
  else
    status="invalid_canonical_materialization"
    freshness_status="cutover_rematerialization_required"
    if [[ ! -d "${target_root}" ]]; then
      status="missing_canonical_materialization"
      freshness_status="cutover_materialization_required"
    fi
    if (( ! json_mode )) && [[ "${emit}" == "true" ]]; then
      printf 'warning: SDK-canonical routing mirror is not valid: %s\n' \
        "${target_root}" >&2
      printf '  refresh only through receipt-bound scripts/aoa-routing-cutover materialize\n' >&2
    fi
  fi

  if (( json_mode )) && [[ "${emit}" == "true" ]]; then
    emit_check_json \
      "aoa-routing" \
      "${status}" \
      "" \
      "${target_root}" \
      "${source_commit}" \
      "${source_commit}" \
      "${mirror_generated_at_utc}" \
      "${refresh_command}" \
      "false" \
      "${synced}" \
      "${freshness_status}" \
      "${manifest_path}"
  elif (( ! json_mode )) && [[ "${emit}" == "true" ]] && [[ "${status}" == "ok" ]]; then
    aoa_note "SDK-canonical routing materialization check complete"
    aoa_note "mirror target: ${target_root}"
  fi

  [[ "${status}" == "ok" ]]
}

resolve_layer_source_rel() {
  local layer="$1"
  local rel_path="$2"
  if [[ "$layer" == "aoa-kag" ]]; then
    case "$rel_path" in
      docs/REASONING_HANDOFF.md)
        printf '%s\n' "mechanics/checkpoint/parts/reasoning-handoff/docs/reasoning-handoff.md"
        return 0
        ;;
      docs/REASONING_HANDOFF_PACK.md)
        printf '%s\n' "mechanics/checkpoint/parts/reasoning-handoff/docs/reasoning-handoff-pack.md"
        return 0
        ;;
      docs/RECURRENCE_REGROUNDING.md)
        printf '%s\n' "mechanics/recurrence/parts/return-regrounding/docs/recurrence-regrounding.md"
        return 0
        ;;
      docs/FEDERATION_KAG_READINESS.md)
        printf '%s\n' "mechanics/boundary-bridge/parts/source-owned-export/docs/federation-kag-readiness.md"
        return 0
        ;;
      docs/COUNTERPART_CONSUMER_CONTRACT.md)
        printf '%s\n' "mechanics/boundary-bridge/parts/counterpart-edge/docs/counterpart-consumer-contract.md"
        return 0
        ;;
      docs/TOS_RETRIEVAL_AXIS_PACK.md)
        printf '%s\n' "mechanics/boundary-bridge/parts/tos-retrieval-axis/docs/tos-retrieval-axis-pack.md"
        return 0
        ;;
      docs/TOS_ZARATHUSTRA_ROUTE_RETRIEVAL_PACK.md)
        printf '%s\n' "mechanics/boundary-bridge/parts/tos-retrieval-axis/docs/tos-zarathustra-route-retrieval-pack.md"
        return 0
        ;;
      generated/federation_spine.min.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/federation-spine/generated/federation_spine.min.json"
        return 0
        ;;
      generated/tiny_consumer_bundle.min.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/tiny-consumer-bundle/generated/tiny_consumer_bundle.min.json"
        return 0
        ;;
      generated/reasoning_handoff_pack.min.json)
        printf '%s\n' "mechanics/checkpoint/parts/reasoning-handoff/generated/reasoning_handoff_pack.min.json"
        return 0
        ;;
      generated/return_regrounding_pack.min.json)
        printf '%s\n' "mechanics/recurrence/parts/return-regrounding/generated/return_regrounding_pack.min.json"
        return 0
        ;;
      generated/technique_lift_pack.min.json)
        printf '%s\n' "mechanics/distillation/parts/technique-lift/generated/technique_lift_pack.min.json"
        return 0
        ;;
      generated/tos_retrieval_axis_pack.min.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/tos-retrieval-axis/generated/tos_retrieval_axis_pack.min.json"
        return 0
        ;;
      generated/tos_text_chunk_map.min.json)
        printf '%s\n' "mechanics/distillation/parts/tos-text-chunk-map/generated/tos_text_chunk_map.min.json"
        return 0
        ;;
      generated/cross_source_node_projection.min.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/cross-source-projection/generated/cross_source_node_projection.min.json"
        return 0
        ;;
      generated/counterpart_federation_exposure_review.min.json)
        printf '%s\n' "mechanics/audit/parts/exposure-review/generated/counterpart_federation_exposure_review.min.json"
        return 0
        ;;
      generated/tos_zarathustra_route_retrieval_pack.min.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/tos-retrieval-axis/generated/tos_zarathustra_route_retrieval_pack.min.json"
        return 0
        ;;
      schemas/federation-spine.schema.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/federation-spine/schemas/federation-spine.schema.json"
        return 0
        ;;
      schemas/tiny-consumer-bundle.schema.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/tiny-consumer-bundle/schemas/tiny-consumer-bundle.schema.json"
        return 0
        ;;
      schemas/reasoning-handoff-pack.schema.json)
        printf '%s\n' "mechanics/checkpoint/parts/reasoning-handoff/schemas/reasoning-handoff-pack.schema.json"
        return 0
        ;;
      schemas/return-regrounding-pack.schema.json)
        printf '%s\n' "mechanics/recurrence/parts/return-regrounding/schemas/return-regrounding-pack.schema.json"
        return 0
        ;;
      schemas/technique-lift-pack.schema.json)
        printf '%s\n' "mechanics/distillation/parts/technique-lift/schemas/technique-lift-pack.schema.json"
        return 0
        ;;
      schemas/tos-retrieval-axis-pack.schema.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/tos-retrieval-axis/schemas/tos-retrieval-axis-pack.schema.json"
        return 0
        ;;
      schemas/tos-text-chunk-map.schema.json)
        printf '%s\n' "mechanics/distillation/parts/tos-text-chunk-map/schemas/tos-text-chunk-map.schema.json"
        return 0
        ;;
      schemas/cross-source-node-projection.schema.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/cross-source-projection/schemas/cross-source-node-projection.schema.json"
        return 0
        ;;
      schemas/counterpart-federation-exposure-review.schema.json)
        printf '%s\n' "mechanics/audit/parts/exposure-review/schemas/counterpart-federation-exposure-review.schema.json"
        return 0
        ;;
      schemas/tos-zarathustra-route-retrieval-pack.schema.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/tos-retrieval-axis/schemas/tos-zarathustra-route-retrieval-pack.schema.json"
        return 0
        ;;
      schemas/counterpart-consumer-contract.schema.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/counterpart-edge/schemas/counterpart-consumer-contract.schema.json"
        return 0
        ;;
      schemas/bridge-envelope.schema.json)
        printf '%s\n' "mechanics/boundary-bridge/parts/tos-retrieval-axis/schemas/bridge-envelope.schema.json"
        return 0
        ;;
    esac
  fi
  if [[ "$layer" == "aoa-evals" ]]; then
    case "$rel_path" in
      docs/TRACE_EVAL_BRIDGE.md)
        printf '%s\n' "mechanics/audit/parts/artifact-verdict-hooks/docs/TRACE_EVAL_BRIDGE.md"
        return 0
        ;;
      docs/RUNTIME_BENCH_PROMOTION_GUIDE.md)
        printf '%s\n' "mechanics/audit/parts/selected-evidence-packets/docs/RUNTIME_BENCH_PROMOTION_GUIDE.md"
        return 0
        ;;
      docs/SELF_AGENT_CHECKPOINT_EVAL_POSTURE.md)
        printf '%s\n' "mechanics/checkpoint/parts/self-agent-posture/docs/SELF_AGENT_CHECKPOINT_EVAL_POSTURE.md"
        return 0
        ;;
      docs/RECURRENCE_PROOF_PROGRAM.md)
        printf '%s\n' "mechanics/recurrence/docs/RECURRENCE_PROOF_PROGRAM.md"
        return 0
        ;;
      generated/runtime_candidate_template_index.min.json)
        printf '%s\n' "mechanics/audit/parts/candidate-readers/generated/runtime_candidate_template_index.min.json"
        return 0
        ;;
      generated/runtime_candidate_intake.min.json)
        printf '%s\n' "mechanics/audit/parts/candidate-readers/generated/runtime_candidate_intake.min.json"
        return 0
        ;;
      examples/runtime_evidence_selection.*.example.json)
        printf '%s\n' "mechanics/audit/parts/selected-evidence-packets/examples/${rel_path#examples/}"
        return 0
        ;;
      examples/artifact_to_verdict_hook.long-horizon-model-tier-orchestra.example.json)
        printf '%s\n' "mechanics/audit/parts/artifact-verdict-hooks/examples/${rel_path#examples/}"
        return 0
        ;;
      examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json)
        printf '%s\n' "mechanics/checkpoint/parts/self-agent-posture/examples/${rel_path#examples/}"
        return 0
        ;;
      examples/artifact_to_verdict_hook.restartable-inquiry-loop.example.json)
        printf '%s\n' "mechanics/checkpoint/parts/restartable-inquiry/examples/${rel_path#examples/}"
        return 0
        ;;
      schemas/runtime-evidence-selection.schema.json)
        printf '%s\n' "mechanics/audit/parts/selected-evidence-packets/schemas/${rel_path#schemas/}"
        return 0
        ;;
      schemas/artifact-to-verdict-hook.schema.json)
        printf '%s\n' "mechanics/audit/parts/artifact-verdict-hooks/schemas/${rel_path#schemas/}"
        return 0
        ;;
      schemas/runtime-candidate-template-index.schema.json)
        printf '%s\n' "mechanics/audit/parts/candidate-readers/schemas/${rel_path#schemas/}"
        return 0
        ;;
    esac
  fi
  printf '%s\n' "$rel_path"
}

write_mirror_manifest() {
  local layer="$1"
  local source_root="$2"
  local target_root="$3"
  local tmp_root="$4"
  shift 4
  python3 - "$layer" "$source_root" "$target_root" "$tmp_root" "$@" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import sys


layer = sys.argv[1]
source_root = Path(sys.argv[2])
target_root = Path(sys.argv[3])
tmp_root = Path(sys.argv[4])
required_files = [Path(item).as_posix() for item in sys.argv[5:]]


def read_json(rel: str) -> object | None:
    path = tmp_root / rel
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def count_records(payload: object, key: str) -> int | None:
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return len(payload[key])
    if isinstance(payload, list):
        return len(payload)
    return None


def git_commit(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", root.as_posix(), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


file_digests: dict[str, str] = {}
for rel in required_files:
    path = tmp_root / rel
    if path.is_file():
        file_digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

catalog = read_json("generated/eval_catalog.min.json")
template_index = read_json("generated/runtime_candidate_template_index.min.json")
intake = read_json("generated/runtime_candidate_intake.min.json")
manifest = {
    "schema": "abyss_stack_federation_mirror_manifest_v1",
    "layer": layer,
    "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "source_root": source_root.as_posix(),
    "target_root": target_root.as_posix(),
    "source_git_commit": git_commit(source_root),
    "required_file_count": len(required_files),
    "required_files": required_files,
    "file_sha256": file_digests,
    "catalog_count": count_records(catalog, "evals"),
    "runtime_candidate_template_count": count_records(template_index, "templates"),
    "runtime_candidate_intake_count": count_records(intake, "templates"),
    "mirror_is_authority": False,
    "refresh_command": "scripts/aoa-sync-federation-surfaces --layer " + layer,
}
manifest_path = tmp_root / "manifest" / "federation_mirror_manifest.json"
manifest_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
PY
}

sync_layer() {
  local layer="$1"
  local source_root target_root tmp_root src_path rel_path source_rel_path config_dir config_path
  local -a required_paths=()

  command -v rsync >/dev/null 2>&1 || aoa_die "rsync is required"

  case "$layer" in
    aoa-agents)
      source_root="${AOA_AGENTS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents"
      ;;
    aoa-routing)
      aoa_die "aoa-routing is materialized only by receipt-bound scripts/aoa-routing-cutover"
      ;;
    aoa-memo)
      source_root="${AOA_MEMO_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo"
      ;;
    aoa-evals)
      source_root="${AOA_EVALS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals"
      ;;
    aoa-playbooks)
      source_root="${AOA_PLAYBOOKS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks"
      ;;
    aoa-kag)
      source_root="${AOA_KAG_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag"
      ;;
    tos-source)
      source_root="${AOA_TOS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/tos-source"
      ;;
    *)
      aoa_die "unsupported layer: ${layer}"
      ;;
  esac

  [[ -d "$source_root" ]] || aoa_die "${layer} root not found: ${source_root}"

  config_dir="$(resolve_federation_config_dir)"
  config_path="${config_dir}/${layer}.yaml"
  [[ -f "$config_path" ]] || aoa_die "federation config not found for ${layer}: ${config_path}"
  while IFS= read -r rel_path; do
    required_paths+=("${rel_path}")
  done < <(load_required_paths "${config_path}")
  if [[ "$layer" == "aoa-evals" ]]; then
    while IFS= read -r rel_path; do
      required_paths+=("${rel_path}")
    done < <(load_bridge_runtime_evidence_refs "${config_dir}")
  fi
  if [[ "$layer" == "aoa-playbooks" ]]; then
    while IFS= read -r rel_path; do
      required_paths+=("${rel_path}")
    done < <(load_bridge_playbook_automation_ref "${config_dir}")
  fi
  (( ${#required_paths[@]} > 0 )) || aoa_die "no required_files found in ${config_path}"

  if [[ "$layer" == "aoa-agents" ]]; then
    local artifact_schema_count=0
    for rel_path in "${required_paths[@]}"; do
      if [[ "$(basename -- "$rel_path")" == artifact.*.schema.json ]]; then
        artifact_schema_count=$((artifact_schema_count + 1))
      fi
    done
    ((artifact_schema_count > 0)) || aoa_die "no artifact schemas found in aoa-agents federation required paths"
  fi

  aoa_note "layer: ${layer}"
  aoa_note "source root: ${source_root}"
  aoa_note "mirror target: ${target_root}"

  tmp_root="$(mktemp -d)"
  trap 'rm -rf "${tmp_root}"' RETURN

  for rel_path in "${required_paths[@]}"; do
    source_rel_path="$(resolve_layer_source_rel "${layer}" "${rel_path}")"
    src_path="${source_root}/${source_rel_path}"
    [[ -f "$src_path" ]] || aoa_die "required source file missing: ${src_path}"
    mkdir -p "${tmp_root}/$(dirname -- "${rel_path}")"
    cp -a "${src_path}" "${tmp_root}/${rel_path}"
  done
  write_mirror_manifest "${layer}" "${source_root}" "${target_root}" "${tmp_root}" "${required_paths[@]}"

  mkdir -p "$(dirname -- "${target_root}")"
  rsync -a --checksum --delete "${tmp_root}/" "${target_root}/"
  rm -rf "${tmp_root}"
  trap - RETURN

  aoa_note "federation surface sync complete for ${layer}"
}

check_layer() {
  local layer="$1"
  local synced="${2:-false}"
  local emit="${3:-true}"
  local source_root target_root rel_path source_rel_path config_dir config_path
  local manifest_path source_commit mirror_commit mirror_generated_at_utc refresh_command
  local status freshness_status sync_recommended check_ok manifest_payload
  local -a required_paths=()
  local -a missing_paths=()
  local -a manifest_fields=()

  if [[ "${layer}" == "aoa-routing" ]]; then
    check_canonical_routing_layer "${synced}" "${emit}"
    return
  fi

  case "$layer" in
    aoa-agents)
      source_root="${AOA_AGENTS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-agents"
      ;;
    aoa-memo)
      source_root="${AOA_MEMO_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo"
      ;;
    aoa-evals)
      source_root="${AOA_EVALS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals"
      ;;
    aoa-playbooks)
      source_root="${AOA_PLAYBOOKS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-playbooks"
      ;;
    aoa-kag)
      source_root="${AOA_KAG_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/aoa-kag"
      ;;
    tos-source)
      source_root="${AOA_TOS_ROOT}"
      target_root="${AOA_STACK_ROOT}/Knowledge/federation/tos-source"
      ;;
    *)
      aoa_die "unsupported layer: ${layer}"
      ;;
  esac

  [[ -d "$source_root" ]] || aoa_die "${layer} root not found: ${source_root}"

  config_dir="$(resolve_federation_config_dir)"
  config_path="${config_dir}/${layer}.yaml"
  [[ -f "$config_path" ]] || aoa_die "federation config not found for ${layer}: ${config_path}"
  while IFS= read -r rel_path; do
    required_paths+=("${rel_path}")
  done < <(load_required_paths "${config_path}")
  if [[ "$layer" == "aoa-evals" ]]; then
    while IFS= read -r rel_path; do
      required_paths+=("${rel_path}")
    done < <(load_bridge_runtime_evidence_refs "${config_dir}")
  fi
  if [[ "$layer" == "aoa-playbooks" ]]; then
    while IFS= read -r rel_path; do
      required_paths+=("${rel_path}")
    done < <(load_bridge_playbook_automation_ref "${config_dir}")
  fi
  (( ${#required_paths[@]} > 0 )) || aoa_die "no required_files found in ${config_path}"

  if (( ! json_mode )) && [[ "$emit" == "true" ]]; then
    aoa_note "check layer: ${layer}"
    aoa_note "source root: ${source_root}"
    aoa_note "mirror target: ${target_root}"
  fi

  for rel_path in "${required_paths[@]}"; do
    source_rel_path="$(resolve_layer_source_rel "${layer}" "${rel_path}")"
    [[ -f "${source_root}/${source_rel_path}" ]] || aoa_die "required source file missing: ${source_root}/${source_rel_path}"
    if [[ ! -f "${target_root}/${rel_path}" ]]; then
      missing_paths+=("${target_root}/${rel_path}")
    fi
  done

  manifest_path="${target_root}/manifest/federation_mirror_manifest.json"
  source_commit="$(git_commit_for_root "${source_root}")"
  mirror_commit=""
  mirror_generated_at_utc=""
  refresh_command=""
  status="ok"
  freshness_status="current"
  sync_recommended="false"
  check_ok=0

  if (( ${#missing_paths[@]} > 0 )); then
    status="missing"
    freshness_status="missing_files"
    sync_recommended="true"
    check_ok=1
    if (( ! json_mode )) && [[ "$emit" == "true" ]]; then
      printf 'warning: missing mirrored files for %s:\n' "${layer}" >&2
      for rel_path in "${missing_paths[@]}"; do
        printf '  %s\n' "${rel_path}"
      done
    fi
  elif [[ ! -f "$manifest_path" ]]; then
    status="missing_manifest"
    freshness_status="missing_manifest"
    sync_recommended="true"
    check_ok=1
    if (( ! json_mode )) && [[ "$emit" == "true" ]]; then
      printf 'warning: mirror manifest missing for %s: %s\n' "${layer}" "${manifest_path}" >&2
    fi
  else
    if ! manifest_payload="$(
      read_manifest_metadata \
        "$manifest_path" \
        "$layer" \
        "$target_root" \
        "${required_paths[@]}" \
        2>/dev/null
    )"; then
      status="invalid_manifest"
      freshness_status="invalid_manifest"
      sync_recommended="true"
      check_ok=1
      if (( ! json_mode )) && [[ "$emit" == "true" ]]; then
        printf 'warning: mirror manifest invalid for %s: %s\n' "${layer}" "${manifest_path}" >&2
      fi
    else
      mapfile -t manifest_fields <<< "$manifest_payload"
      mirror_commit="${manifest_fields[0]:-}"
      mirror_generated_at_utc="${manifest_fields[1]:-}"
      refresh_command="${manifest_fields[2]:-}"
      if [[ -n "$source_commit" && -z "$mirror_commit" ]]; then
        status="missing_source_commit"
        freshness_status="missing_source_commit"
        sync_recommended="true"
        check_ok=1
        if (( ! json_mode )) && [[ "$emit" == "true" ]]; then
          printf 'warning: mirror manifest has no source_git_commit for %s: %s\n' "${layer}" "${manifest_path}" >&2
        fi
      elif [[ -n "$source_commit" && -n "$mirror_commit" && "$source_commit" != "$mirror_commit" ]]; then
        status="stale"
        freshness_status="source_commit_mismatch"
        sync_recommended="true"
        check_ok=1
        if (( ! json_mode )) && [[ "$emit" == "true" ]]; then
          printf 'warning: mirror manifest source_git_commit differs for %s\n' "${layer}" >&2
          printf '  source checkout: %s\n' "${source_commit}" >&2
          printf '  mirror manifest: %s\n' "${mirror_commit}" >&2
        fi
      elif [[ -z "$source_commit" ]]; then
        freshness_status="source_commit_unavailable"
      fi
    fi
  fi

  if (( json_mode )) && [[ "$emit" == "true" ]]; then
    emit_check_json "${layer}" "${status}" "${source_root}" "${target_root}" \
      "${source_commit}" "${mirror_commit}" "${mirror_generated_at_utc}" "${refresh_command}" \
      "${sync_recommended}" "${synced}" "${freshness_status}" "${manifest_path}" "${missing_paths[@]}"
  elif (( ! json_mode )) && [[ "$emit" == "true" ]] && (( check_ok == 0 )); then
    aoa_note "federation surface check complete for ${layer}"
  fi
  return "${check_ok}"
}

overall_status=0
for layer in "${layers[@]}"; do
  if [[ "${layer}" == "aoa-routing" ]] && (( sync_if_stale )); then
    aoa_die "aoa-routing cannot be repaired by federation sync; use receipt-bound scripts/aoa-routing-cutover materialize"
  fi
  if (( check_mode )); then
    if (( sync_if_stale )); then
      if check_layer "$layer" false false; then
        check_layer "$layer" false true || overall_status=1
      else
        if (( json_mode )); then
          sync_layer "$layer" >&2
        else
          sync_layer "$layer"
        fi
        if ! check_layer "$layer" true true; then
          overall_status=1
        fi
      fi
    else
      if ! check_layer "$layer" false true; then
        overall_status=1
      fi
    fi
  else
    sync_layer "$layer"
  fi
done

exit "${overall_status}"
