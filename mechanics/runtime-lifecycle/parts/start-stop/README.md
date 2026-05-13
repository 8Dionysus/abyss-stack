# Start And Stop

Routes `scripts/aoa-up`, `scripts/aoa-down`, `scripts/aoa-warmup`,
`compose/profiles/`, and `compose/presets/`. The implementation bodies live in
`mechanics/runtime-lifecycle/parts/start-stop/aoa_up.sh` and
`mechanics/runtime-lifecycle/parts/start-stop/aoa_down.sh`; model warmup lives
in `mechanics/runtime-lifecycle/parts/start-stop/aoa_warmup.sh` because it is a
post-start lifecycle action, not a benchmark or promotion claim.

Starting runtime services remains an explicit operator action.
