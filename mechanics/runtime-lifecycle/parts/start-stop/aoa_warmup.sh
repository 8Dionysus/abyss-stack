#!/usr/bin/env bash
set -euo pipefail

MECHANIC_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${MECHANIC_SCRIPT_DIR}/../../../.." && pwd)"
SCRIPTS_DIR="${SOURCE_ROOT}/scripts"
# shellcheck source=scripts/aoa-lib.sh
source "${SCRIPTS_DIR}/aoa-lib.sh"

aoa_parse_profile_args "$@"
aoa_resolve_modules

has_module() {
  local target="$1"
  local module
  for module in "${AOA_PROFILE_MODULE_NAMES[@]}"; do
    [[ "$module" == "$target" ]] && return 0
  done
  return 1
}

is_enabled() {
  case "${1,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

if ! is_enabled "$AOA_OLLAMA_WARMUP_ENABLED"; then
  aoa_note "ollama warmup disabled"
fi

if has_module "32-llamacpp-inference.yml"; then
  if ! is_enabled "$AOA_LLAMACPP_WARMUP_ENABLED"; then
    aoa_note "llama.cpp warmup disabled"
    exit 0
  fi
  command -v curl >/dev/null 2>&1 || aoa_die "curl is required"
  wait_deadline=$((SECONDS + AOA_LLAMACPP_WARMUP_WAIT_S))
  until curl -fsS --max-time 5 "$AOA_LLAMACPP_WARMUP_URL" >/dev/null 2>&1; do
    if (( SECONDS >= wait_deadline )); then
      aoa_note "warn llama.cpp warmup skipped because ${AOA_LLAMACPP_WARMUP_URL} did not become ready in ${AOA_LLAMACPP_WARMUP_WAIT_S}s"
      exit 0
    fi
    sleep 2
  done
  aoa_note "llama.cpp warmup complete"
  exit 0
fi

if ! has_module "30-local-inference.yml"; then
  aoa_note "skip model warmup because selected profiles do not include a warmup-managed inference module"
  exit 0
fi

command -v curl >/dev/null 2>&1 || aoa_die "curl is required"
command -v python >/dev/null 2>&1 || aoa_die "python is required"

wait_deadline=$((SECONDS + AOA_OLLAMA_WARMUP_WAIT_S))
tags_url="${AOA_OLLAMA_WARMUP_URL%/}/api/tags"
chat_url="${AOA_OLLAMA_WARMUP_URL%/}/api/chat"
ps_url="${AOA_OLLAMA_WARMUP_URL%/}/api/ps"

until curl -fsS --max-time 5 "$tags_url" >/dev/null 2>&1; do
  if (( SECONDS >= wait_deadline )); then
    aoa_note "warn ollama warmup skipped because ${tags_url} did not become ready in ${AOA_OLLAMA_WARMUP_WAIT_S}s"
    exit 0
  fi
  sleep 2
done

aoa_note "warming ollama model ${AOA_OLLAMA_WARMUP_MODEL}"
warmup_payload="$(python - <<'PY'
import json
import os

payload = {
    "model": os.environ["AOA_OLLAMA_WARMUP_MODEL"],
    "messages": [{"role": "user", "content": "reply with ok"}],
    "stream": False,
    "think": False,
    "keep_alive": os.environ["AOA_OLLAMA_WARMUP_KEEP_ALIVE"],
    "options": {
        "num_predict": 8,
        "num_thread": int(os.environ["AOA_OLLAMA_WARMUP_NUM_THREAD"]),
        "num_batch": int(os.environ["AOA_OLLAMA_WARMUP_NUM_BATCH"]),
    },
}
num_ctx = os.environ.get("AOA_OLLAMA_WARMUP_NUM_CTX", "").strip()
if num_ctx:
    payload["options"]["num_ctx"] = int(num_ctx)
print(json.dumps(payload))
PY
)"

warmup_response="$(curl -fsS --max-time "${AOA_OLLAMA_WARMUP_TIMEOUT_S}" \
  -H 'Content-Type: application/json' \
  -d "${warmup_payload}" \
  "$chat_url")" || {
  aoa_note "warn ollama warmup request failed for ${AOA_OLLAMA_WARMUP_MODEL}"
  exit 0
}

WARMUP_RESPONSE="$warmup_response" python - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["WARMUP_RESPONSE"])
message = payload.get("message") or {}
content = message.get("content") or payload.get("response") or ""
if not isinstance(content, str):
    print("warn ollama warmup returned a non-string response")
    sys.exit(0)
PY

loaded_models="$(curl -fsS --max-time 10 "$ps_url")" || {
  aoa_note "warn ollama warmup could not confirm loaded models via /api/ps"
  exit 0
}

if LOADED_MODELS="$loaded_models" python - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["LOADED_MODELS"])
model_name = os.environ["AOA_OLLAMA_WARMUP_MODEL"]
models = payload.get("models", [])
for entry in models:
    if entry.get("model") == model_name or entry.get("name") == model_name:
        sys.exit(0)
sys.exit(1)
PY
then
  aoa_note "ollama warmup complete for ${AOA_OLLAMA_WARMUP_MODEL}"
else
  aoa_note "warn ollama warmup finished but ${AOA_OLLAMA_WARMUP_MODEL} was not visible in /api/ps"
fi
