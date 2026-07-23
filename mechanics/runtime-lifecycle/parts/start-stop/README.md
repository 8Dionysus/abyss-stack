# Start And Stop

Routes `scripts/aoa-up`, `scripts/aoa-down`, `scripts/aoa-warmup`,
`scripts/aoa-apply-resource-guards`, `compose/profiles/`, and `compose/presets/`.
The implementation bodies live in
`mechanics/runtime-lifecycle/parts/start-stop/aoa_up.sh` and
`mechanics/runtime-lifecycle/parts/start-stop/aoa_down.sh`; model warmup lives
in `mechanics/runtime-lifecycle/parts/start-stop/aoa_warmup.sh` because it is a
post-start lifecycle action, not a benchmark or promotion claim.

Warmup is profile-aware: the canonical `llama.cpp` local-worker path warms by
default when selected, while the retained Ollama fallback lane requires
`AOA_OLLAMA_WARMUP_ENABLED=true`.

Starting runtime services remains an explicit operator action.

Use `scripts/aoa-apply-resource-guards --dry-run` before applying staged
resource overlays. The command records pre-apply status under
`${AOA_STACK_ROOT}/Logs/resource-guards/latest/`, refuses to reload, recreate,
or restart while `abyss-machine processes game-guard --json` is active unless
`--force` is passed, and rechecks `aoa-status --resource-guards` after the apply
action.
An unreadable live cgroup fact fails closed as `live_resource_unknown`; the
apply route does not turn missing evidence into permission to recreate the
stack.
It also captures pre/post `podman stats --no-stream` and memory/PSI snapshots in
the same directory so the operator can compare the tuned live state without
reconstructing evidence from scrollback. The apply route also captures
pre/post `aoa-status --service-selection --json` and fails if service selection
degrades after the reload or restart. It records protected user-unit state for
host TTS, dictation, TTS keep-warm, and the stack runner, and fails if any of
those units are no longer active after applying the staged guards.
Resource-plan gate evidence is written as `pre-resource-plan.json`; after a
real apply, the wrapper also records `post-resource-plan.json` for the same host
resource route.
The default method is `recreate`: it reloads the user unit with a temporary
`AOA_UP_FORCE_RECREATE=1` manager environment so `aoa-up` runs
`podman-compose up -d --force-recreate` and existing containers receive staged
cgroup changes. Pass `--method reload` for a lighter best-effort apply or
`--method restart` for a full down/up window.
Before the live apply, the wrapper also runs
`abyss-machine resource plan --class medium --kind generic --unattended --json`;
non-forced apply refuses when that current sampled plan blocks.
Use `--wait-game-guard-clear --wait-resource-plan-clear` for a supervised
safe-window apply that polls both the game guard and the host resource plan
instead of forcing through active load. Tune the wait with `--wait-timeout-sec`
and `--wait-poll-sec`; the default timeout is one hour.

Use `docs/LIVE_RUNTIME_CUTOVER_PACKET.md` before promoting a deployed seam into
the live runtime loop.
