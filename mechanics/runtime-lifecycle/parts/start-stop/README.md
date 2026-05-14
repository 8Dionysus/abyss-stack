# Start And Stop

Routes `scripts/aoa-up`, `scripts/aoa-down`, `scripts/aoa-warmup`,
`compose/profiles/`, and `compose/presets/`. The implementation bodies live in
`mechanics/runtime-lifecycle/parts/start-stop/aoa_up.sh` and
`mechanics/runtime-lifecycle/parts/start-stop/aoa_down.sh`; model warmup lives
in `mechanics/runtime-lifecycle/parts/start-stop/aoa_warmup.sh` because it is a
post-start lifecycle action, not a benchmark or promotion claim.

Warmup is profile-aware: the canonical `llama.cpp` local-worker path warms by
default when selected, while the retained Ollama fallback lane requires
`AOA_OLLAMA_WARMUP_ENABLED=true`.

Starting runtime services remains an explicit operator action.

Use `docs/LIVE_RUNTIME_CUTOVER_PACKET.md` before promoting a deployed seam into
the live runtime loop.
